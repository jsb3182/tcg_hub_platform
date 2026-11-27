"""Compare Project Ignis's current regional files to the release's officially reconciled snapshots."""
import hashlib
import logging
import os
import time
from datetime import datetime, timezone
from urllib.error import HTTPError
from .feeds import backoff


FILES = {"OCG": "OCG.lflist.conf", "TCG": "0TCG.lflist.conf"}
BASE = "https://raw.githubusercontent.com/ProjectIgnis/LFLists/master/"


def check_files(http):
    checks = {}
    cooldown = http.root / ".yugioh-limits-retry-at"
    if cooldown.is_file() and float(cooldown.read_text("ascii")) > time.time():
        return dict.fromkeys(FILES)
    for region, name in FILES.items():
        try:
            path = http.get(BASE + name, ttl=86400, size=128_000)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            fetched_on = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).date()
            checks[region] = (digest, fetched_on)
        except HTTPError as error:
            code = error.code
            delay = backoff(error.headers)
            error.close()
            checks[region] = None
            if code in (429, 503):
                staged = cooldown.with_suffix(".new")
                staged.write_text(str(time.time() + max(delay, 60)), encoding="ascii")
                os.replace(staged, cooldown)
                break
        except (OSError, ValueError):
            checks[region] = None
    for region in FILES:
        if not checks.get(region):
            logging.getLogger(__name__).warning("%s regional restriction list could not be confirmed", region)
            checks[region] = None
    return checks


def save_checks(db, checks):
    for region, observed in checks.items():
        if observed is None:
            db.execute("UPDATE yugioh_limit_list SET evidence_status='UNAVAILABLE' WHERE region=%s", (region,))
            continue
        digest, fetched_on = observed
        # A changed list must be reconciled to canonical card IDs and its published effective date.
        # Preserve the last verified snapshot and its date on change, network loss, or replay.
        db.execute("""
            UPDATE yugioh_limit_list
               SET evidence_status=CASE WHEN file_sha256=%s THEN 'VERIFIED' ELSE 'CHANGED' END,
                   verified_on=CASE WHEN file_sha256=%s THEN %s ELSE verified_on END
             WHERE region=%s AND %s >= verified_on AND %s <= current_date
            """, (digest, digest, fetched_on, region, fetched_on, fetched_on))
