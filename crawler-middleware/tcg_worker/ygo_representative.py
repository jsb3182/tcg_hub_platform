"""Import already acquired YGOPRODeck JPEGs as reviewed card references, without network access."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import zipfile

from . import local_art
from .jobs import connect
from .media import publish


def import_bundle(db, media, path, digest):
    counts = {"files": 0, "matched": 0, "cached": 0, "newLinks": 0}
    with path.open("rb") as stream:
        if not re.fullmatch("[0-9a-f]{64}", digest) or hashlib.file_digest(stream, "sha256").hexdigest() != digest:
            raise ValueError("Incorrect representative bundle SHA-256")
        stream.seek(0)
        with zipfile.ZipFile(stream) as archive:
            entries = archive.infolist()
            if (not 0 < len(entries) <= 200 or len({e.filename for e in entries}) != len(entries)
                    or any(not re.fullmatch(r"[1-9][0-9]{0,9}\.jpg", e.filename)
                           or not 0 < e.file_size <= 512_000 for e in entries)):
                raise ValueError("Invalid representative JPEG bundle")
            for entry in entries:
                # Validate the published original bytes independently of the supplied bundle digest.
                original = archive.read(entry)
                raw_hash = hashlib.sha256(original).hexdigest()
                with db.transaction():
                    if not db.execute("SELECT pg_try_advisory_xact_lock(%s)", (local_art.LOCK,)).fetchone()[0]:
                        raise RuntimeError("Image worker busy. Rerun this same bundle.")
                    if not db.execute("""SELECT EXISTS(SELECT FROM collection_control WHERE scheduler_enabled AND crawler_enabled)
                            AND EXISTS(SELECT FROM feed_source WHERE provider='CATALOG' AND source_key='YUGIOH'
                                       AND enabled AND policy_note IS NULL)""").fetchone()[0]:
                        raise RuntimeError("Operator paused catalog collection")
                    asset = db.execute("""SELECT source_url FROM yugioh_provider_art WHERE provider_card_id=%s
                                          AND source_sha256=%s AND language IS NOT NULL""",
                                       (entry.filename[:-4], raw_hash)).fetchone()
                    if not asset:
                        raise ValueError("JPEG has no matching reviewed representative")
                    url, = asset
                    cards = db.execute("""SELECT c.id FROM card c JOIN catalog_ygo_provider_reference r ON r.card_id=c.id
                                          WHERE r.source_url=%s FOR SHARE OF c""", (url,)).fetchall()
                    counts["files"] += 1
                    if not cards:
                        continue
                    counts["matched"] += len(cards)
                    db.execute("""INSERT INTO catalog_art_file(game_code,source_url) VALUES('YUGIOH',%s)
                                  ON CONFLICT(source_url) DO NOTHING""", (url,))
                    fid, storage, known_hash = db.execute("""SELECT id,storage_key,source_sha256 FROM catalog_art_file
                            WHERE game_code='YUGIOH' AND source_url=%s FOR UPDATE""", (url,)).fetchone()
                    if not storage or known_hash != raw_hash or not (media / storage).is_file():
                        if shutil.disk_usage(media).free < 768 * 1024 * 1024:
                            raise RuntimeError("Insufficient media storage")
                        pixels = local_art.webp(original)
                        key = publish(media, "cards", pixels)
                        db.execute("""UPDATE catalog_art_file SET storage_key=%s,source_sha256=%s,capture_hash=%s::bit(64),
                                      checked_at=now(),next_attempt='infinity',failures=0,last_error=NULL WHERE id=%s""",
                                   (key, raw_hash, local_art.capture_hash(pixels), fid))
                        counts["cached"] += 1
                    linked = db.execute("""INSERT INTO catalog_art_card(card_id,file_id)
                            SELECT unnest(%s::bigint[]),%s ON CONFLICT DO NOTHING""", ([c[0] for c in cards], fid))
                    counts["newLinks"] += linked.rowcount
    return counts


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("jpeg_bundle", type=Path)
    cli.add_argument("sha256")
    args = cli.parse_args()
    media = Path(os.getenv("MEDIA_ROOT", "/var/lib/tcg-hub/media"))
    with connect() as conn:
        conn.autocommit = True
        print(json.dumps(import_bundle(conn, media, args.jpeg_bundle, args.sha256)))
