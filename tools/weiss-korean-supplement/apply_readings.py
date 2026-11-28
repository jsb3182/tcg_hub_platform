"""Apply missing Korean reference names to the identified English Weiss printings."""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
from urllib.parse import quote

from psycopg.errors import LockNotAvailable, QueryCanceled

from tcg_worker.jobs import connect
from tcg_worker.translation import TRANSLATION_LOCK
from tcg_worker.weiss_readings import memory_key


DATA = Path(__file__).with_name("readings.jsonl")
DATA_SHA256 = "36947c9686c864c62dcc5aeff1b869304d7624ee69640d686afee1c4b786e43d"
MARKS = re.compile(r"[+−%♡♥☆★♪♫【】《》]|\d+")


def load_readings(path=DATA):
    # Compare checkout-independent UTF-8/LF bytes, including the final line break.
    body = path.read_text(encoding="utf8")
    if sha256(body.encode()).hexdigest() != DATA_SHA256:
        raise ValueError("Unexpected reading data SHA-256")
    rows = [json.loads(line) for line in body.splitlines()]
    numbers = set()
    units = {}
    for row in rows:
        number, original, korean = row["number"], row["originalName"], row["koreanReading"]
        family = number.split("/", 1)[0]
        digest = memory_key("name", original, family)
        source_url = "https://en.ws-tcg.com/cardlist/cardsearch/exec?cardno=" + quote(number, safe="")
        if (not family or "/" not in number or number in numbers or not row["product"]
                or row["sourceUrl"] != source_url or digest.hex() != row["sourceHash"]
                or not re.search("[가-힣]", korean) or re.search("[A-Za-zぁ-ヿ一-鿿]", korean)
                or MARKS.findall(original) != MARKS.findall(korean)
                or units.setdefault(digest, korean) != korean):
            raise ValueError(f"Invalid English printing or reading revision: {number}")
        numbers.add(number)
    if len(numbers) != 390 or len(units) != 372:
        raise ValueError("Unexpected printing or translation count")
    return rows


PRINTING = """
    SELECT c.id,r.name,r.name_basis,r.basis,
           nullif(c.specs->'names'->>'ko','') IS NOT NULL OR EXISTS (
               SELECT 1 FROM card_translation t WHERE t.card_id=c.id AND t.lang='ko'
               AND nullif(t.name,'') IS NOT NULL),
           c.effect IS NOT NULL AND r.effect IS NULL AND nullif(c.specs->'texts'->>'ko','') IS NULL
    FROM card c JOIN pack p ON p.id=c.pack_id AND p.game_code=c.game_code
    JOIN feed_source s ON s.id=c.source_id AND s.provider='CATALOG' AND s.source_key='WEISS'
    JOIN card_korean_reading r ON r.card_id=c.id
    WHERE c.game_code='WEISS' AND c.status='PUBLISHED' AND c.specs->>'language'='en'
          AND c.legacy_key=%s AND c.number=%s AND c.name=%s AND c.original_name=%s
          AND c.source_url=%s AND p.name=%s
"""
MEMORY = "SELECT original,translated FROM weiss_translation_memory WHERE source_hash=%s"


def apply_batch(db, rows, write, stats, changed_units):
    for row in rows:
        stats["examined"] += 1
        number, original, korean = row["number"], row["originalName"], row["koreanReading"]
        record = db.execute(
            PRINTING + (" FOR UPDATE OF c,r" if write else ""),
            ("catalog:WEISS:en:" + number, number, original, original, row["sourceUrl"], row["product"]),
        ).fetchone()
        if record is None:
            stats["missingOrSourceChanged"] += 1
            continue
        card_id, existing, name_basis, basis, has_review_or_edition, needs_effect = record
        if has_review_or_edition or "CURATED_TRANSLATION" in (basis, name_basis):
            stats["protectedName"] += 1
            continue
        if existing == korean and name_basis == "MACHINE_TRANSLATION":
            stats["alreadyMatched"] += 1
            continue
        if existing is not None:
            stats["protectedName"] += 1
            continue
        digest = bytes.fromhex(row["sourceHash"])
        cached = db.execute(MEMORY + (" FOR UPDATE" if write else ""), (digest,)).fetchone()
        if cached is None or cached[0] != original or cached[1] not in (None, korean):
            stats["missingFullMemoOrDifferentValue"] += 1
            continue
        if cached[1] is None and digest not in changed_units:
            if write:
                updated = db.execute("""
                    UPDATE weiss_translation_memory SET translated=%s
                    WHERE source_hash=%s AND original=%s AND translated IS NULL
                    """, (korean, digest, original)).rowcount
                if updated != 1:
                    raise RuntimeError("Translation memory changed during the update")
            changed_units.add(digest)
            stats["memoryUpdated"] += 1
        if write:
            updated = db.execute("""
                UPDATE card_korean_reading SET name=%s,name_basis='MACHINE_TRANSLATION',
                    weiss_draft_due_at=CASE WHEN %s THEN coalesce(weiss_draft_due_at,due_at)
                                           ELSE weiss_draft_due_at END, due_at=NULL
                WHERE card_id=%s AND name IS NULL AND basis<>'CURATED_TRANSLATION'
                """, (korean, needs_effect, card_id)).rowcount
            if updated != 1:
                raise RuntimeError("Printing reading changed during the update")
        stats["namesUpdated"] += 1


def apply(db, rows, write=False):
    stats = Counter(examined=0, memoryUpdated=0, namesUpdated=0, alreadyMatched=0)
    # The worker uses the same session lock. Short transactions allow normal catalog updates.
    if not db.execute("SELECT pg_try_advisory_lock(%s)", (TRANSLATION_LOCK,)).fetchone()[0]:
        raise LockNotAvailable("Translation worker is busy")
    try:
        changed_units = set()
        for start in range(0, len(rows), 24):
            with db.transaction():
                db.execute("SET LOCAL lock_timeout='1200ms'")
                db.execute("SET LOCAL statement_timeout='10s'")
                apply_batch(db, rows[start:start+24], write, stats, changed_units)
        return dict(stats)
    finally:
        db.execute("SELECT pg_advisory_unlock(%s)", (TRANSLATION_LOCK,))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--verify-data", action="store_true", help="check the bundled readings without a database")
    modes.add_argument("--apply", action="store_true", help="commit eligible changes; the default previews them")
    args = parser.parse_args()
    rows = load_readings()
    if args.verify_data:
        print(json.dumps({"prints": len(rows), "nameUnits": len({r["sourceHash"] for r in rows})}))
        return 0
    try:
        with connect() as db:
            db.autocommit = True
            counts = apply(db, rows, args.apply)
    except (LockNotAvailable, QueryCanceled):
        print("Catalog or translation worker busy. Retry after the current batch.", file=sys.stderr)
        return 3
    print(json.dumps({"mode": "apply" if args.apply else "preview", "counts": counts}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
