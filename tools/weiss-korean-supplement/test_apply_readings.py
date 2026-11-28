"""Run with the worker on PYTHONPATH. TCG_TEST_DSN enables the temporary PostgreSQL tables."""
from collections import defaultdict
import os
import unittest

import psycopg
from psycopg.errors import LockNotAvailable

from apply_readings import apply, load_readings, TRANSLATION_LOCK


class DatasetTests(unittest.TestCase):
    def test_all_published_identifiers_and_shared_title_keys(self):
        rows = load_readings()
        self.assertEqual(len({row["number"] for row in rows}), 390)
        self.assertEqual(len({row["sourceHash"] for row in rows}), 372)
        self.assertEqual(
            next(row["koreanReading"] for row in rows if row["number"] == "5HY/W101-E067"),
            "가벼운 놀림, 나카노 이치카",
        )
        self.assertTrue(all("id" not in row and "evidence" in row for row in rows))


@unittest.skipUnless(os.environ.get("TCG_TEST_DSN"), "set TCG_TEST_DSN to a disposable PostgreSQL database")
class PostgresTests(unittest.TestCase):
    def setUp(self):
        self.db = psycopg.connect(os.environ["TCG_TEST_DSN"], autocommit=True)
        self.addCleanup(self.db.close)
        self.db.execute("SET search_path=pg_temp")
        for table, columns in {
            "feed_source": "id int primary key,provider text,source_key text",
            "pack": "id int primary key,game_code text,name text",
            "card": """id int primary key,pack_id int,source_id int,game_code text,status text,specs jsonb,
                       legacy_key text,number text,name text,original_name text,source_url text,effect text""",
            "card_translation": "card_id int,lang text,name text",
            "card_korean_reading": """card_id int primary key,name text,name_basis text,basis text,effect text,
                                      due_at timestamptz,weiss_draft_due_at timestamptz""",
            "weiss_translation_memory": "source_hash bytea primary key,original text,translated text",
        }.items():
            self.db.execute(f"CREATE TEMP TABLE {table} ({columns})")
        self.db.execute("INSERT INTO feed_source VALUES (1,'CATALOG','WEISS')")
        self.rows = load_readings()

    def seed(self, rows):
        for index, row in enumerate(rows, 1):
            self.db.execute("INSERT INTO pack VALUES (%s,'WEISS',%s)", (index, row["product"]))
            self.db.execute("""
                INSERT INTO card VALUES (%s,%s,1,'WEISS','PUBLISHED','{"language":"en"}',
                                         %s,%s,%s,%s,%s,'Original ability')
                """, (index, index, "catalog:WEISS:en:"+row["number"], row["number"],
                      row["originalName"], row["originalName"], row["sourceUrl"]))
            self.db.execute("""
                INSERT INTO card_korean_reading VALUES (%s,NULL,NULL,'MACHINE_TRANSLATION',NULL,now(),NULL)
                """, (index,))
            self.db.execute("""
                INSERT INTO weiss_translation_memory VALUES (%s,%s,NULL) ON CONFLICT DO NOTHING
                """, (bytes.fromhex(row["sourceHash"]), row["originalName"]))

    def test_preview_repeat_shared_names_and_pending_effect(self):
        shared = defaultdict(list)
        for row in self.rows:
            shared[row["sourceHash"]].append(row)
        pair = next(values[:2] for values in shared.values() if len(values) > 1)
        self.seed(pair)
        self.db.execute("UPDATE card_korean_reading SET effect='확인한 효과' WHERE card_id=1")
        counts = apply(self.db, pair)
        self.assertEqual((counts["namesUpdated"], counts["memoryUpdated"]), (2, 1))
        self.assertEqual(self.db.execute("SELECT count(name) FROM card_korean_reading").fetchone()[0], 0)
        self.assertEqual(apply(self.db, pair, True), counts)
        self.assertEqual(apply(self.db, pair, True),
                         dict(examined=2, memoryUpdated=0, namesUpdated=0, alreadyMatched=2))
        self.assertEqual(self.db.execute("""
            SELECT effect,name_basis,due_at IS NULL,weiss_draft_due_at IS NOT NULL
            FROM card_korean_reading ORDER BY card_id
            """).fetchall(), [("확인한 효과", "MACHINE_TRANSLATION", True, False),
                              (None, "MACHINE_TRANSLATION", True, True)])

    def test_source_identity_existing_display_and_different_memory(self):
        rows = list({row["sourceHash"]: row for row in self.rows}.values())[:12]
        self.seed(rows)
        self.db.execute("UPDATE card_korean_reading SET name='기존 이름' WHERE card_id=1")
        self.db.execute("UPDATE card_korean_reading SET basis='CURATED_TRANSLATION' WHERE card_id=2")
        self.db.execute("INSERT INTO card_translation VALUES (3,'ko','운영자 검수')")
        self.db.execute("""UPDATE card SET specs=specs||'{"names":{"ko":"발행사 이름"}}' WHERE id=4""")
        self.db.execute("UPDATE pack SET name='Different product' WHERE id=5")
        self.db.execute("UPDATE card SET status='PENDING' WHERE id=6")
        self.db.execute("UPDATE card SET original_name='Source edit' WHERE id=7")
        self.db.execute("UPDATE card SET source_url='https://example.invalid/' WHERE id=8")
        self.db.execute("DELETE FROM weiss_translation_memory WHERE source_hash=%s",
                        (bytes.fromhex(rows[8]["sourceHash"]),))
        self.db.execute("UPDATE weiss_translation_memory SET translated='기존 메모' WHERE source_hash=%s",
                        (bytes.fromhex(rows[9]["sourceHash"]),))
        self.db.execute("UPDATE card SET legacy_key='manual:foo' WHERE id=11")
        self.db.execute("UPDATE card SET number='Different print' WHERE id=12")
        counts = apply(self.db, rows, True)
        self.assertEqual(counts, dict(examined=12, namesUpdated=0, memoryUpdated=0, alreadyMatched=0,
                                      protectedName=4, missingOrSourceChanged=6, missingFullMemoOrDifferentValue=2))
        self.assertEqual(self.db.execute("SELECT name FROM card_translation").fetchone()[0], "운영자 검수")
        self.assertEqual(self.db.execute("SELECT translated FROM weiss_translation_memory WHERE translated IS NOT NULL")
                         .fetchall(), [("기존 메모",)])

    def test_busy_worker(self):
        with psycopg.connect(os.environ["TCG_TEST_DSN"], autocommit=True) as worker:
            worker.execute("SELECT pg_advisory_lock(%s)", (TRANSLATION_LOCK,))
            with self.assertRaises(LockNotAvailable):
                apply(self.db, self.rows[:1], True)


if __name__ == "__main__":
    unittest.main()
