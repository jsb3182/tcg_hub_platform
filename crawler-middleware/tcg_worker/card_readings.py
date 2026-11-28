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
                    UPDATE card_korean_reading SET name=%s,effect=%s,basis='CURATED_TRANSLATION',due_at=NULL,
                        name_basis='CURATED_TRANSLATION',effect_basis='CURATED_TRANSLATION',weiss_draft_due_at=NULL
                    WHERE card_id=%s AND (name,effect,basis,due_at,weiss_draft_due_at)
                        IS DISTINCT FROM (%s,%s,'CURATED_TRANSLATION',NULL::timestamptz,NULL::timestamptz)
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


def fill_readings(db, get_model, stop, limit, *, weiss_only=False):
    from . import weiss_readings
    with db.cursor(row_factory=dict_row) as cur:
        cards = cur.execute("""
            SELECT c.id,c.game_code,c.legacy_key,c.name,c.number,c.effect,c.source_url,c.specs->>'language' AS lang,
                   nullif(c.specs->'names'->>'ko','') IS NULL AND existing.name IS NULL AS need_name,
                   nullif(c.specs->'texts'->>'ko','') IS NULL AND existing.effect IS NULL AS need_effect,
                   c.edit_version,r.due_at
            FROM pending_korean_card_reading r JOIN card c ON c.id=r.card_id JOIN card_korean_reading existing ON existing.card_id=c.id
            WHERE r.due_at<=now() AND (NOT %s OR c.game_code='WEISS')
            ORDER BY CASE WHEN c.game_code='WEISS' THEN 1 ELSE 0 END,r.due_at,r.card_id LIMIT %s
            """, (weiss_only,limit)).fetchall()
    written = 0
    for card in cards:
        if stop.is_set():
            break
        try:
            curated = curated_reading(card)
            if curated:
                name, effect, basis = curated["name"], curated["effect"], "CURATED_TRANSLATION"
                name_basis = effect_basis = basis
            elif card["game_code"] == "WEISS":
                name = effect = name_basis = effect_basis = None
                if weiss_readings.eligible(card):
                    def translate(kind, source, family):
                        if stop.is_set():
                            return None
                        return weiss_readings.lookup(db,get_model,kind,source,family)
                    name,effect,name_basis,effect_basis = weiss_readings.translated_fields(card,translate)
                basis = "MACHINE_TRANSLATION"
            else:
                model = get_model()
                name = korean_field(model, card["name"], card["lang"], 320,card["game_code"]) if card["need_name"] else None
                effect = korean_field(model, card["effect"], card["lang"], 8000,card["game_code"]) if card["need_effect"] else None
                basis = "GLOSSARY_TRANSLATED"
                name_basis = effect_basis = basis
        except (RuntimeError, ValueError, OSError, ImportError) as error:
            LOG.warning("Korean reading deferred for card %s (%s)", card["id"], type(error).__name__)
            db.execute("""UPDATE card_korean_reading SET
                              due_at=CASE WHEN due_at IS NOT NULL THEN now()+interval '15 minutes' END,
                              weiss_draft_due_at=CASE WHEN due_at IS NULL THEN now()+interval '15 minutes' END
                          WHERE card_id=%s AND coalesce(due_at,weiss_draft_due_at)=%s""",
                       (card["id"],card["due_at"]))
            break
        if stop.is_set():
            break
        written += db.execute("""
            UPDATE card_korean_reading r SET name=coalesce(%s,r.name),effect=coalesce(%s,r.effect),basis=%s,
                name_basis=CASE WHEN %s::text IS NOT NULL THEN %s WHEN r.name IS NOT NULL THEN coalesce(r.name_basis,r.basis) END,
                effect_basis=CASE WHEN %s::text IS NOT NULL THEN %s WHEN r.effect IS NOT NULL THEN coalesce(r.effect_basis,r.basis) END,
                due_at=NULL,weiss_draft_due_at=NULL FROM card c
            WHERE c.id=r.card_id AND c.id=%s AND c.edit_version=%s AND coalesce(r.due_at,r.weiss_draft_due_at)=%s
               AND c.name=%s AND c.effect IS NOT DISTINCT FROM %s AND c.source_url IS NOT DISTINCT FROM %s
            """, (name,effect,basis,name,name_basis,effect,effect_basis,
                  card["id"],card["edit_version"],card["due_at"],card["name"],card["effect"],card["source_url"])).rowcount
    return written
