import json
import os
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import psycopg
from psycopg import sql

from tcg_worker.catalog_sources.transport import CatalogHTTP
from tcg_worker.catalog_sources.ygo_kr_print import korean_prints, save_korean_prints, seed_from_cache


def entry(numbers, filename="101.json"):
    return {"names": {"ko": "수록 카드"}, "printings": {"ko": numbers}, "texts": {}, "file": filename}


class KoreanPrintingTests(unittest.TestCase):
    def test_actual_product_requires_korean_print_number_and_card_identity(self):
        cards = {"4844": entry(["LOB-K119", "LOB-EN119"]), "4007": entry(["LOB-K119"]),
                 "22706": entry(["LOCH-KR017"]), "2": entry(["FAKE-JP001"])}
        rows = {r["cid"]: r for r in korean_prints(cards)}
        self.assertEqual("2003-12-09", rows[4844]["released"])
        self.assertEqual("240fad99-f00a-41ed-99e9-26656d0d677c", rows[4844]["product"])
        self.assertIsNone(rows[4007]["released"])
        self.assertIsNone(rows[22706]["released"])
        self.assertNotIn(2, rows)

    def test_alternate_art_uses_its_own_source_and_earliest_confirmed_product(self):
        card = entry(["A-KR001", "B-KR002"])
        card["alternates"] = [entry(["C-KR003"], "102.json")]
        index = {"cards": {"99": {"B-KR002": 0, "C-KR003": 1}},
                 "products": [["later", "2021-01-01"], ["earlier", "2020-01-01"]]}
        row, = korean_prints({"99": card}, index)
        self.assertEqual(("C-KR003", "102.json", "earlier"), (row["number"], row["file"], row["product"]))
        card["alternates"][0]["names"] = {}
        self.assertEqual("B-KR002", korean_prints({"99": card}, index)[0]["number"])


@unittest.skipUnless(os.environ.get("TCG_TEST_DSN"), "requires an isolated database")
class KoreanPrintingDatabaseTests(unittest.TestCase):
    def test_cache_seed_idempotency_then_authoritative_correction_and_withdrawal(self):
        with psycopg.connect(os.environ["TCG_TEST_DSN"]) as db, db.transaction(force_rollback=True):
            schema = sql.Identifier("kprint_" + uuid.uuid4().hex)
            db.execute(sql.SQL("create schema {}").format(schema))
            db.execute(sql.SQL("set local search_path to {}").format(schema))
            migration = Path(__file__).resolve().parents[2] / "backend/src/main/resources/db/migration/V33__yugioh_korean_print.sql"
            db.execute(migration.read_text("utf-8"))
            db.execute("create table feed_source(provider text,source_key text,game_code text,state text,last_success_at date)")
            db.execute("insert into feed_source values('CATALOG','YUGIOH','YUGIOH','RUNNING',current_date)")
            with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"CATALOG_CACHE_ROOT": tmp}):
                http = CatalogHTTP()
                cache = Path(tmp) / ".ygo-printed-editions-v3.json"
                cache.write_text(json.dumps({"revision": "a"*40, "names": {"4844": entry(["LOB-K119"]),
                                                                            "22706": entry(["LOCH-KR017"])}}))
                with self.assertRaisesRegex(ValueError, "idle"):
                    seed_from_cache(db, http)
                db.execute("update feed_source set state='IDLE',last_success_at=null")
                with self.assertRaisesRegex(ValueError, "first successful"):
                    seed_from_cache(db, http)
                db.execute("update feed_source set last_success_at=current_date")
                result = seed_from_cache(db, http)
                self.assertEqual((2, 1), (result["cards"], result["dated"]))
                cache.unlink()
                self.assertEqual("ALREADY_PRESENT", seed_from_cache(db, http)["status"])
            save_korean_prints(db, "b"*40, [])
            self.assertEqual(2, db.execute("select count(*) from yugioh_korean_print").fetchone()[0])
            corrected = korean_prints({"4844": entry(["EXP-KR009"])})
            save_korean_prints(db, "b"*40, corrected)
            save_korean_prints(db, "c"*40, corrected)
            self.assertEqual([("EXP-KR009", None, "b"*40)], db.execute(
                "select number,product_released_on,yaml_revision from yugioh_korean_print").fetchall())
            self.assertEqual(("IDLE", True), db.execute(
                "select state,last_success_at=current_date from feed_source").fetchone())
