import json
import os
import threading
import unittest
import uuid
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from tcg_worker import feeds
from tcg_worker.sync import sync_source


class PublisherAccessTests(unittest.TestCase):
    def test_us_scheduled_and_diagnostic_adapter_stops_before_network(self):
        with patch.object(feeds, "check_robots") as robots, patch.object(feeds, "download") as download:
            with self.assertRaises(feeds.FetchError) as error:
                feeds.fetch_feed("OFFICIAL_NEWS", "yugioh-en", {"modified": "old"})
        self.assertTrue(error.exception.blocked)
        robots.assert_not_called()
        download.assert_not_called()


@unittest.skipUnless(os.environ.get("TCG_TEST_DSN"), "set TCG_TEST_DSN to test PostgreSQL/PostGIS")
class CatalogNewsTests(unittest.TestCase):
    def setUp(self):
        self.dsn = os.environ["TCG_TEST_DSN"]
        self.schema = "catalog_news_" + uuid.uuid4().hex
        self.db = psycopg.connect(self.dsn, autocommit=True)
        self.addCleanup(self.db.close)
        identifier = sql.Identifier(self.schema)
        self.db.execute(sql.SQL("CREATE SCHEMA {}").format(identifier))
        self.addCleanup(self.db.execute, sql.SQL("DROP SCHEMA {} CASCADE").format(identifier))
        self.db.execute(sql.SQL("SET search_path TO {},public").format(identifier))
        migrations = Path(__file__).resolve().parents[2] / "backend/src/main/resources/db/migration"
        for f in sorted(migrations.glob("V*.sql"), key=lambda path: int(path.name[1:].split("__")[0])):
            self.db.execute(f.read_text(encoding="utf-8"))
        self.sid = self.db.execute("SELECT id FROM feed_source WHERE provider='CATALOG' AND source_key='YUGIOH'").fetchone()[0]

    def scan(self, records):
        with self.db.cursor(row_factory=dict_row) as cur:
            source = cur.execute("""
                UPDATE feed_source SET state='RUNNING',last_seen=0,last_added=0 WHERE id=%s RETURNING *
            """, (self.sid,)).fetchone()
        with patch("tcg_worker.sync.connect", lambda: psycopg.connect(self.dsn, options=f"-c search_path={self.schema},public")), \
             patch("tcg_worker.catalog_sources.iter_catalog", return_value=records):
            sync_source(source, threading.Event())
        state, cursor = self.db.execute("SELECT state,cursor_value FROM feed_source WHERE id=%s", (self.sid,)).fetchone()
        return state, json.loads(cursor or "{}")

    @staticmethod
    def entry(index, pack):
        return {"external_id": str(index), "name": f"Card {index}", "source_url": "https://example.invalid/card",
                "specs": {"names": {"ko": f"카드 {index}", "ja": f"カード {index}"}},
                "pack_code": pack, "pack_name": pack}

    def rows(self):
        return self.db.execute("SELECT id,status,payload,original_language,translation_due_at FROM feed_item").fetchall()

    def test_baseline_selects_only_one_verified_recent_tcg_set(self):
        today = self.db.execute("SELECT (now() AT TIME ZONE 'Asia/Seoul')::date").fetchone()[0]
        rows = [{**self.entry(i, name), "pack_tcg_date": (today + timedelta(days=days)).isoformat()}
                for i, (name, days) in enumerate([("Future Set", 1), ("Recent Set", -2), ("Older Set", -10),
                                                  ("Too Old", -31), ("Same Date Set", -2)])]
        rows.append({**self.entry(100, "No Set Date"), "release_date": today.isoformat()})
        self.assertEqual(self.scan(rows)[0], "OK")
        [(item, status, payload, lang, due)] = self.rows()
        self.assertEqual((status, lang, due), ("PUBLISHED", "ko", None))
        self.assertIn("Recent Set", payload["title"])
        self.assertIn((today-timedelta(days=2)).isoformat(), payload["summary"])
        source_url = self.db.execute("SELECT source_url FROM feed_item WHERE id=%s", (item,)).fetchone()[0]
        self.assertEqual(source_url, "https://ygoprodeck.com/pack/recent%20set/")
        foreign = list(self.db.execute("SELECT lang,summary FROM feed_item_translation WHERE item_id=%s", (item,)))
        self.assertEqual({lang for lang, _ in foreign}, {"en", "ja"})
        self.assertTrue(all("YGOPRODeck" in summary and "Recent Set" in summary for _, summary in foreign))
        self.assertEqual(self.scan(rows)[0], "OK")
        self.assertEqual(len(self.rows()), 1)

    def test_completed_scan_deduplicates_baseline_retries_and_uses_no_model(self):
        baseline = [self.entry(i, "Initial Set") for i in range(225)]
        state, checkpoint = self.scan(baseline)
        self.assertEqual((state, checkpoint["count"], self.rows()), ("OK", 225, []))
        self.assertEqual(self.scan(baseline), (state, checkpoint))
        new_cards = [self.entry(i, "Another Set") for i in range(225, 425)]

        def incomplete():
            yield from new_cards
            raise RuntimeError("Interrupted after a committed batch")

        self.assertEqual(self.scan(incomplete()), ("ERROR", checkpoint))
        self.assertEqual(self.rows(), [])
        # A late failure in the status transaction rolls back the digest and both watermarks.
        self.db.execute("ALTER TABLE feed_source ADD CONSTRAINT fail_test_finish CHECK (source_key<>'YUGIOH' OR state<>'OK')")
        full = baseline + new_cards + [self.entry(425, "수록 팩 미확인")]
        self.assertEqual(self.scan(full), ("ERROR", checkpoint))
        self.assertEqual(self.rows(), [])
        self.db.execute("ALTER TABLE feed_source DROP CONSTRAINT fail_test_finish")
        state, finished = self.scan(full)
        self.assertEqual((state, finished["count"]), ("OK", 426))
        [(item, status, payload, original, due)] = self.rows()
        self.assertEqual((status, payload["kind"], original, due), ("PUBLISHED", "NEWS", "ko", None))
        self.assertIn("카드 항목 201건과 팩 1개", payload["summary"])
        self.assertIn("Another Set", payload["summary"])
        self.assertRegex(payload["summary"], r"카드 · 카드 \d+")
        rendered = dict(self.db.execute("SELECT lang,summary FROM feed_item_translation WHERE item_id=%s", (item,)))
        self.assertIn("201 card entries and 1 set.", rendered["en"])
        self.assertIn("カード201件とパック1件", rendered["ja"])
        self.assertRegex(rendered["ja"], r"カード · カード \d+")
        self.assertEqual(self.scan(full), (state, finished))
        self.assertEqual(len(self.rows()), 1)

        # A newly identified set on an existing row is a set-only update.
        state, _ = self.scan([*full[:-1], self.entry(425, "Identified Set")])
        self.assertEqual(state, "OK")
        self.assertIn("카드 항목 0건과 팩 1개", max(self.rows(), key=lambda row: row[0])[2]["summary"])
