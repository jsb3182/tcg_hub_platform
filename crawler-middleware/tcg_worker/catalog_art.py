"""Queue a bounded daily batch of provider-approved, locally rehosted representative artwork."""
import logging
import os
import re
import shutil
import tempfile
from pathlib import Path
from urllib.error import HTTPError

from .catalog_sources.transport import CatalogHTTP
from .jobs import enqueue

def queue_yugioh_art(db, source_id, after, stop):
    http=CatalogHTTP()
    spool=Path(os.environ.get("SPOOL_ROOT","/var/lib/tcg-hub/spool"))
    sql="""SELECT v.id,c.specs->>'representativeArt' FROM card c JOIN card_variant v ON v.card_id=c.id
        WHERE c.source_id=%s AND c.status='PUBLISHED' AND v.position=0 AND v.sheet_id IS NULL
          AND c.specs ? 'representativeArt' AND v.id>%s
          AND NOT EXISTS(SELECT 1 FROM media_job j WHERE j.variant_id=v.id)
        ORDER BY v.id LIMIT 12"""
    rows=db.execute(sql,(source_id,after)).fetchall()
    if not rows and after:
        rows=db.execute(sql,(source_id,0)).fetchall()
    with tempfile.TemporaryDirectory(dir=http.root) as scratch:
        jpg=Path(scratch)/"card.jpg"
        for variant,url in rows:
            if stop.is_set(): break
            after=variant
            if not re.fullmatch(r"https://images\.ygoprodeck\.com/images/cards_small/[0-9]+\.jpg",url):
                continue
            try:
                original=http.get(url,ttl=365*86400,size=512_000,delay=1)
                shutil.copyfile(original,jpg)
                with db.transaction():
                    locked=db.execute("""SELECT v.id FROM card_variant v JOIN card c ON c.id=v.card_id
                        WHERE v.id=%s AND c.status='PUBLISHED' AND v.sheet_id IS NULL FOR UPDATE OF v FOR SHARE OF c""",
                        (variant,)).fetchone()
                    if locked and not db.execute("SELECT 1 FROM media_job WHERE variant_id=%s",(variant,)).fetchone():
                        enqueue(db,spool,variant,jpg)
            except HTTPError as exc:
                exc.close()
                if exc.code!=404:
                    logging.getLogger(__name__).warning("Representative art deferred (HTTP %s)",exc.code)
                    break
            except (OSError,ValueError) as exc:
                logging.getLogger(__name__).warning("Representative art deferred (%s)",type(exc).__name__)
                break
    return after
