import json
import os
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import psycopg
from psycopg import sql

from tcg_worker import feeds
from tcg_worker.store_notice import scheduled_event
from tcg_worker.sync import save_news


TOURNAMENT = "주말 합성 매장전\n- 대회 시작 일시: 2026-12-05 (토) 오후 12:30 (KST)"
RESTOCK = "신상품 합성 공지\n• 입고 예정 일시： 2026/12/03 20시 05분"


def timeline(*posts):
    """Pass fixture bytes to the actual X adapter, without opening a connection."""
    data = [{"id": str(number), "text": text, "created_at": "2026-11-30T13:20:00Z"}
            for number, text in posts]
    body = json.dumps({"data": data, "meta": {"result_count": len(data)}}).encode()
    with patch.dict(os.environ, {"X_BEARER_TOKEN": "fixture"}), \
            patch.object(feeds, "download", return_value=(body, {})):
        return feeds.x_news("FixtureShop", {"uid": "99"}).items


class StoreNoticeParserTests(unittest.TestCase):
    def test_explicit_korean_schedules_use_korea_time(self):
        cases = [
            (TOURNAMENT, "TOURNAMENT", "2026-12-05T03:30:00+00:00"),
            (RESTOCK, "RESTOCK", "2026-12-03T11:05:00+00:00"),
            ("대회 일시: 2028년 2월 29일 (화요일) 오전 12시 05분 (한국 시간)",
             "TOURNAMENT", "2028-02-28T15:05:00+00:00"),
        ]
        for text, expected_kind, expected_utc in cases:
            with self.subTest(text=text):
                kind, starts_at = scheduled_event(text)
                self.assertEqual(kind, expected_kind)
                self.assertEqual(starts_at.utcoffset().total_seconds(), 9 * 3600)
                self.assertEqual(starts_at.astimezone(timezone.utc).isoformat(), expected_utc)

    def test_ambiguous_invalid_and_unconfirmed_notices_only_remain_news(self):
        for text in (
            "대회 접수 마감: 2026-12-05 12:30", "일시: 2026-12-05 12:30",
            "대회 일시: 12-05 12:30", "대회 일시: 2026-12-05",
            "대회 일시: 2026-02-29 12:30", "입고 일시: 2026-12-03 24:00",
            "대회 일시: 2026-12-05 오후 13시", "대회 일시: 2026-12-05 오전 0시",
            "대회 일시: 2026-12-05 09:60", "대회 일시: 2026-12-05 12:30 PST",
            TOURNAMENT + "\n" + RESTOCK, TOURNAMENT + "\n행사 취소", "기상으로 연기\n" + TOURNAMENT,
            "루머\n" + RESTOCK, "미확인 소식\n" + TOURNAMENT, RESTOCK + "\n입고일 미정",
            "미확정\n" + RESTOCK, "잠정 일정\n" + TOURNAMENT, "Unconfirmed\n" + RESTOCK,
        ):
            with self.subTest(text=text):
                self.assertIsNone(scheduled_event(text))

    def test_timeline_keeps_post_time_separate_from_schedule_and_links_to_the_post(self):
        [item, cancelled] = timeline((502, RESTOCK), (501, TOURNAMENT + "\n행사 취소"))
        self.assertEqual(item.external_id, "502")
        self.assertEqual(item.url, "https://x.com/FixtureShop/status/502")
        self.assertEqual(item.published, datetime(2026, 11, 30, 13, 20, tzinfo=timezone.utc))
        self.assertEqual(item.event, ("RESTOCK", datetime(2026, 12, 3, 11, 5, tzinfo=timezone.utc)))
        self.assertIn("20:05 KST", item.summary)
        self.assertEqual(cancelled.external_id, "501")
        self.assertIsNone(cancelled.event)


@unittest.skipUnless(os.environ.get("TCG_TEST_DSN"), "set TCG_TEST_DSN to test PostgreSQL/PostGIS")
class StoreNoticeDatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = psycopg.connect(os.environ["TCG_TEST_DSN"], autocommit=True)
        cls.addClassCleanup(cls.db.close)
        schema = sql.Identifier("store_notice_" + uuid4().hex)
        cls.db.execute(sql.SQL("CREATE SCHEMA {}").format(schema))
        cls.addClassCleanup(cls.db.execute, sql.SQL("DROP SCHEMA {} CASCADE").format(schema))
        cls.db.execute(sql.SQL("SET search_path TO {}, public").format(schema))
        migrations = Path(__file__).resolve().parents[2] / "backend/src/main/resources/db/migration"
        for path in sorted(migrations.glob("V*.sql"), key=lambda f: int(f.name[1:].split("__")[0])):
            cls.db.execute(path.read_text(encoding="utf-8"))

    def setUp(self):
        self.enterContext(self.db.transaction(force_rollback=True))
        self.shop, self.other_shop = [row[0] for row in self.db.execute("""
            INSERT INTO store(name,address,location)
            SELECT s,'합성 주소',ST_SetSRID(ST_MakePoint(127,37.5),4326)::geography
              FROM unnest(ARRAY['합성 매장 A','합성 매장 B']) s RETURNING id
        """)]

    def source(self, provider, store, *, auto_publish=False):
        source_id = self.db.execute("""
            INSERT INTO feed_source(provider,source_key,store_id,game_code,auto_publish)
            VALUES (%s,'FixtureShop',%s,'ONEPIECE',%s) RETURNING id
        """, (provider, store, auto_publish)).fetchone()[0]
        return {"id": source_id, "provider": provider, "store_id": store, "auto_publish": auto_publish}

    def events(self):
        return self.db.execute("""
            SELECT i.external_id,i.source_url,e.category,e.starts_at,e.store_id,e.game_code,e.status,i.status
              FROM calendar_event e JOIN feed_item i ON i.id=e.feed_item_id
             ORDER BY i.external_id
        """).fetchall()

    def test_linked_manual_review_source_records_both_types_once_with_original_provenance(self):
        source = self.source("X", self.shop)
        items = timeline((503, "매장 안내"), (502, RESTOCK), (501, TOURNAMENT))
        self.assertEqual(save_news(self.db, source, items), 3)
        expected = [
            ("501", "https://x.com/FixtureShop/status/501", "TOURNAMENT",
             datetime(2026, 12, 5, 3, 30, tzinfo=timezone.utc), self.shop, "ONEPIECE", "PENDING", "PENDING"),
            ("502", "https://x.com/FixtureShop/status/502", "RESTOCK",
             datetime(2026, 12, 3, 11, 5, tzinfo=timezone.utc), self.shop, "ONEPIECE", "PENDING", "PENDING"),
        ]
        self.assertEqual(self.events(), expected)
        self.assertEqual(save_news(self.db, source, items), 0)
        self.assertEqual(self.events(), expected)
        self.assertEqual(self.db.execute("SELECT count(*) FROM feed_item WHERE source_id=%s",
                                         (source["id"],)).fetchone()[0], 3)

    def test_published_duplicate_cannot_retarget_the_store_or_replace_the_notice(self):
        source = self.source("X", self.shop, auto_publish=True)
        [post] = timeline((508, RESTOCK))
        self.assertEqual(save_news(self.db, dict(source, store_id=self.other_shop), [post]), 1)
        [original] = self.events()
        self.assertEqual(original[4:], (self.shop, "ONEPIECE", "PUBLISHED", "PUBLISHED"))
        modified = replace(post, url="https://example.invalid/changed", title="바뀐 제목",
                           event=scheduled_event(TOURNAMENT))
        self.assertEqual(save_news(self.db, source, [modified]), 0)
        self.assertEqual(self.events(), [original])
        self.assertEqual(self.db.execute("SELECT payload->>'title' FROM feed_item WHERE source_id=%s",
                                         (source["id"],)).fetchone()[0], post.title)

    def test_only_a_registered_x_source_with_a_store_can_produce_events(self):
        [post] = timeline((510, TOURNAMENT))
        for registered in (self.source("X", None), self.source("DCINSIDE", self.shop)):
            with self.subTest(provider=registered["provider"], store_id=registered["store_id"]):
                stale_claim = dict(registered, provider="X", store_id=self.other_shop)
                self.assertEqual(save_news(self.db, stale_claim, [post]), 1)
                self.assertEqual(self.events(), [])


if __name__ == "__main__":
    unittest.main()
