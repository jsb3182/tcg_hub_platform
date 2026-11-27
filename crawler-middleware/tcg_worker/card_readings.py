"""Build explicitly attributed Korean reading aids from foreign catalog printings."""
from collections import Counter
from functools import lru_cache
from hashlib import sha256
import json
import logging
from pathlib import Path
import re

from psycopg.rows import dict_row
from .card_glossary import translate_line

LOG = logging.getLogger(__name__)
CURATED = Path(__file__).parent / "catalog_sources/wiki_data/weiss_readings.json"


@lru_cache(maxsize=1)
def curated_index():
    rows = json.loads(CURATED.read_text(encoding="utf-8"))
    return {r["catalogKey"]: r for r in rows}


def curated_reading(card):
    row = curated_index().get(card["legacy_key"])
    if row is None or row["originalName"] != card["name"] or row["sourceUrl"] != card["source_url"]:
        return None
    original = (card["effect"] or "").replace("\r\n", "\n").encode()
    return row if sha256(original).hexdigest() == row["originalEffectSha256"] else None


def seed_curated_readings(db):
    keys=list(curated_index())
    if not keys:
        return
    with db.cursor(row_factory=dict_row) as cur:
        cards=cur.execute("""
            SELECT c.id,c.legacy_key,c.name,c.effect,c.source_url FROM card c JOIN card_korean_reading r ON r.card_id=c.id
            WHERE c.legacy_key=ANY(%s) FOR UPDATE OF c,r
            """, (keys,)).fetchall()
        for card in cards:
            row=curated_reading(card)
            if row:
                cur.execute("""
                    UPDATE card_korean_reading SET name=%s,effect=%s,basis='CURATED_TRANSLATION',due_at=NULL
                    WHERE card_id=%s AND (name,effect,basis,due_at) IS DISTINCT FROM (%s,%s,'CURATED_TRANSLATION',NULL::timestamptz)
                    """, (row["name"],row["effect"],card["id"],row["name"],row["effect"]))


def korean_field(model, value, lang, limit, game=None):
    if not value or not value.strip() or len(value) > limit:
        return None
    # Keep each line's rule markers, numbers and signs. Reject suspicious omissions
    # instead of serving a modified cost, quantity or stat as the translation.
    lines = []
    for line in value.splitlines():
        if not line.strip():
            lines.append("")
            continue
        result = translate_line(model,game,line.strip(),lang) if game else model.translate(line.strip(),lang,"ko")
        if not result or not re.search(r"[가-힣]", result) or re.search(r"[ぁ-ヿ]", result):
            return None
        numbers = r"[+-]?\d+(?:[.,]\d+)*%?"
        if Counter(re.findall(numbers, line)) != Counter(re.findall(numbers, result)):
            return None
        lines.append(result)
    translated = "\n".join(lines).strip()
    return translated if 0 < len(translated) <= limit else None


def fill_readings(db, get_model, stop, limit):
    with db.cursor(row_factory=dict_row) as cur:
        cards = cur.execute("""
            SELECT c.id,c.game_code,c.legacy_key,c.name,c.effect,c.source_url,c.specs->>'language' AS lang,
                   nullif(c.specs->'names'->>'ko','') IS NULL AS need_name,
                   nullif(c.specs->'texts'->>'ko','') IS NULL AS need_effect,
                   c.edit_version,r.due_at
            FROM pending_korean_card_reading r JOIN card c ON c.id=r.card_id
            WHERE r.due_at<=now() ORDER BY r.due_at,r.card_id LIMIT %s
            """, (limit,)).fetchall()
    written = 0
    for card in cards:
        if stop.is_set():
            break
        try:
            curated = curated_reading(card)
            if curated:
                name, effect, basis = curated["name"], curated["effect"], "CURATED_TRANSLATION"
            else:
                model = get_model()
                name = korean_field(model, card["name"], card["lang"], 320,card["game_code"]) if card["need_name"] else None
                effect = korean_field(model, card["effect"], card["lang"], 8000,card["game_code"]) if card["need_effect"] else None
                basis = "GLOSSARY_TRANSLATED"
        except (RuntimeError, ValueError, OSError, ImportError) as error:
            LOG.warning("Korean reading deferred for card %s (%s)", card["id"], type(error).__name__)
            db.execute("UPDATE card_korean_reading SET due_at=now()+interval '15 minutes' WHERE card_id=%s AND due_at=%s",
                       (card["id"],card["due_at"]))
            break
        if stop.is_set():
            break
        written += db.execute("""
            UPDATE card_korean_reading r SET name=%s,effect=%s,basis=%s,due_at=NULL FROM card c
            WHERE c.id=r.card_id AND c.id=%s AND c.edit_version=%s AND r.due_at=%s
            """, (name,effect,basis,card["id"],card["edit_version"],card["due_at"])).rowcount
    return written
