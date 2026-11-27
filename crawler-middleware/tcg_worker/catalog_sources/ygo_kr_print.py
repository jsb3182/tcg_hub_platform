"""One attested Korean printing per Konami card, independent from deck legality."""
from functools import lru_cache
import gzip
from itertools import chain
import json
from pathlib import Path
import re

from psycopg.types.json import Jsonb


NUMBER = re.compile(r"[A-Z0-9][A-Z0-9-]{0,23}-K(?:R[A-Z]?)?[0-9]{2,4}[A-Z]?")
FILE = re.compile(r"(?:kdb)?[0-9]+\.json")


@lru_cache(maxsize=1)
def product_index():
    with gzip.open(Path(__file__).with_name("ygo_kr_products.json.gz"), "rt", encoding="ascii") as stream:
        return json.load(stream)


def korean_prints(cards, index=None):
    index = product_index() if index is None else index
    rows = []
    for cid, canonical in cards.items():
        if not re.fullmatch(r"[1-9][0-9]{0,9}", cid):
            continue
        product_numbers = index["cards"].get(cid, {})
        choices = []
        for entry in chain((canonical,), canonical.get("alternates", ())):
            filename = entry["file"]
            if not FILE.fullmatch(filename) or not entry["names"].get("ko"):
                continue
            for number in entry["printings"].get("ko", ()):
                if not isinstance(number, str) or not NUMBER.fullmatch(number):
                    continue
                position = product_numbers.get(number)
                product, released = index["products"][position] if position is not None else (None, None)
                # Known product dates sort first. Undated evidence stays usable on its own.
                choices.append((released is None, released or "", number, filename, product))
        if choices:
            _, released, number, filename, product = min(choices)
            rows.append({"cid": int(cid), "number": number, "file": filename,
                         "released": released or None, "product": product})
    return rows


def save_korean_prints(db, revision, rows):
    # A source outage or an unrecognizable format cannot withdraw the whole dataset.
    if not rows:
        return
    db.execute("""
        WITH incoming AS MATERIALIZED (
            SELECT * FROM jsonb_to_recordset(%s) AS r(cid bigint,number text,file text,released date,product uuid)
        ), withdrawn AS (
            DELETE FROM yugioh_korean_print k WHERE NOT EXISTS (SELECT FROM incoming i WHERE i.cid=k.konami_id)
        )
        INSERT INTO yugioh_korean_print AS target(konami_id,number,yaml_revision,yaml_file,product_released_on,product_id)
            SELECT cid,number,%s,file,released,product FROM incoming
        ON CONFLICT(konami_id) DO UPDATE SET number=excluded.number,yaml_revision=excluded.yaml_revision,
            yaml_file=excluded.yaml_file,product_released_on=excluded.product_released_on,product_id=excluded.product_id
        WHERE (target.number,target.yaml_file,target.product_released_on,target.product_id)
            IS DISTINCT FROM (excluded.number,excluded.yaml_file,excluded.product_released_on,excluded.product_id)
        """, (Jsonb(rows), revision))


def seed_from_cache(db, http):
    from .card_names import _ygo_snapshot

    with http.scan("YUGIOH"), db.transaction():
        source = db.execute("""
            SELECT state,last_success_at FROM feed_source
             WHERE provider='CATALOG' AND source_key='YUGIOH' AND game_code='YUGIOH' FOR UPDATE NOWAIT
            """).fetchone()
        if not source or not source[1] or source[0] == "RUNNING":
            raise ValueError("Wait for the first successful YUGIOH import and an idle catalog")
        count = db.execute("SELECT count(*) FROM yugioh_korean_print").fetchone()[0]
        if count:
            return {"status": "ALREADY_PRESENT", "cards": count}
        snapshot = _ygo_snapshot(http.root / ".ygo-printed-editions-v3.json")
        if not snapshot:
            raise ValueError("No validated local YUGIOH printed-edition snapshot")
        rows = korean_prints(snapshot["names"])
        if not rows:
            raise ValueError("No Korean printed numbers in the cached snapshot")
        save_korean_prints(db, snapshot["revision"], rows)
        return {"status": "SEEDED_FROM_CACHE", "revision": snapshot["revision"], "cards": len(rows),
                "dated": sum(row["released"] is not None for row in rows)}
