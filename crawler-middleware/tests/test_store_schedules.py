import os
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import psycopg
from psycopg import sql
from tcg_worker import store_schedules as schedules

KEY = "onepiece-kr-events"
SHOP = "테스트 TCG"
ADDRESS = "서울특별시 관악구 검증로 123-2"


def html(times):
    head = "<tr><th>지역</th><th>주소</th><th>점포 명</th><th>개최일</th><th>시간</th></tr>"
    rows = [
        f"<tr><td>서울</td><td>{ADDRESS}, 3층</td><td>{SHOP}</td><td>2026-11-28(토)</td><td>{time}</td></tr>"
        for time in times
    ]
    return (
        "<html><div class='sub_p_post_detail'><div class='top_title'><div class='tit'>공식 행사</div></div></div><table>"
        + head
        + "".join(rows)
        + "</table></html>"
    )


class ScheduleTests(unittest.TestCase):
    def test_no_guess_from_general_announcement_and_malformed_date(self):
        self.assertIsNone(schedules.event_table("<html>모든 매장, 2026년 11월</html>"))
        for bad in (
            html(["18:00"]).replace("28(토)", "28(일)"),
            html(["오후 중"]),
            html(["24:00"]),
        ):
            with self.assertRaises(schedules.FetchError):
                schedules.event_table(bad)
        with self.assertRaises(schedules.FetchError):
            schedules.event_table("<html>잠시 후</html>", "공식 행사")
        (event,) = schedules.event_table(html(["19:30 (취소)"]), "공식 행사")
        self.assertEqual(event.starts.isoformat(), "2026-11-28T19:30:00+09:00")
        self.assertTrue(event.cancelled)
        self.assertEqual(
            event.shop, schedules.shop_key("테스트티씨지", "서울 관악구 검증로 123-2")
        )
        self.assertNotEqual(
            event.shop, schedules.shop_key("테스트티씨지", "서울 관악구 검증로 123")
        )

    def test_publisher_index_uses_only_local_numeric_notice_links(self):
        links = b'<a class="item" href="https://example.org/events/view.do?brdno=123"><span class="tit">X</span></a>'
        self.assertFalse(schedules.event_links(links))
        doc = '<a class="item" href="events/view.do?brdno=123"><span class="tit">11월 스탠다드</span></a>'
        self.assertEqual(schedules.event_links(doc), {"123": "11월 스탠다드"})
        queue = {"pending": [["123", "공식 행사"]]}
        with patch.object(schedules, "public", return_value=html(["19:30"])):
            self.assertEqual(len(schedules.fetch(KEY, queue).events), 1)
        queue = {"pending": [["123", "이전 제목"], ["456", "다음 공지"]]}
        with patch.object(schedules, "public", return_value=html(["19:30"])):
            deferred = schedules.fetch(KEY, queue)
            self.assertIsNotNone(deferred.deferred)
            self.assertEqual(deferred.cursor["pending"], [["456", "다음 공지"]])
        with patch.object(
            schedules,
            "public",
            side_effect=schedules.FetchError("limit", retry_after=600),
        ):
            with self.assertRaises(schedules.FetchError):
                schedules.fetch(KEY, queue)

    def test_explicit_correction_uses_replacement_only(self):
        corrected = html(["<del>18:30</del>19:00"])
        (event,) = schedules.event_table(corrected)
        self.assertEqual(event.starts.hour, 19)
        self.assertFalse(event.cancelled)
        with self.assertRaises(schedules.FetchError):
            schedules.event_table(html(["<s>18:30</s>"]))


@unittest.skipUnless(os.getenv("TCG_TEST_DSN"), "PostgreSQL/PostGIS")
class ScheduleStorageTests(unittest.TestCase):
    def test_reschedule_retract_preserve_manual_other_sources_and_operator_changes(
        self,
    ):
        db = psycopg.connect(os.environ["TCG_TEST_DSN"], autocommit=True)
        self.addCleanup(db.close)
        schema = sql.Identifier("publisher_schedule_" + uuid.uuid4().hex)
        db.execute(sql.SQL("CREATE SCHEMA {}").format(schema))
        self.addCleanup(db.execute, sql.SQL("DROP SCHEMA {} CASCADE").format(schema))
        db.execute(sql.SQL("SET search_path TO {},public").format(schema))
        migrations = (
            Path(__file__).resolve().parents[2]
            / "backend/src/main/resources/db/migration"
        )
        for file in sorted(
            migrations.glob("V*.sql"), key=lambda f: int(f.name[1:].split("__")[0])
        ):
            db.execute(file.read_text("utf8"))
        store = db.execute(
            """insert into store(name,address,location) values(%s,%s,ST_SetSRID(ST_MakePoint(127,37),4326)) returning id""",
            (SHOP, ADDRESS),
        ).fetchone()[0]
        sid = db.execute(
            "select id from feed_source where source_key=%s", (KEY,)
        ).fetchone()[0]
        official = db.execute(
            "select id from feed_source where source_key='onepiece-kr-official-shops'"
        ).fetchone()[0]
        shop = schedules.shop_key(SHOP, ADDRESS)
        registry = schedules.Schedule("onepiece-kr-official-shops", {}, shops={shop})
        schedules.save(db, official, registry)
        self.assertTrue(
            db.execute("select public_store_official(%s,null)", (store,)).fetchone()[0]
        )
        db.execute(
            "insert into calendar_event(store_id,game_code,title,category,starts_at,status) values(%s,'ONEPIECE','수동 일정','TOURNAMENT',now(),'PUBLISHED')",
            (store,),
        )

        def apply(times, notice="123"):
            return schedules.save(
                db,
                sid,
                schedules.Schedule(
                    KEY,
                    {},
                    notice=notice,
                    title="공식 행사",
                    events=schedules.event_table(html(times)),
                ),
            )

        self.assertEqual(apply(["18:00", "19:30"]), (2, 2))
        self.assertEqual(apply(["18:00", "19:30"]), (2, 0))
        apply(["19:30"], "456")
        db.execute(
            "update calendar_event set title='운영자 수정' where schedule_notice='123' and schedule_slot like '%18:00:00%'"
        )
        apply(["20:00"])
        states = db.execute(
            "select title,status from calendar_event where store_id=%s order by id",
            (store,),
        ).fetchall()
        self.assertCountEqual(
            states,
            [
                ("수동 일정", "PUBLISHED"),
                ("운영자 수정", "PUBLISHED"),
                ("공식 행사", "REJECTED"),
                ("공식 행사", "PUBLISHED"),
                ("공식 행사", "PUBLISHED"),
            ],
        )
        self.assertEqual(
            schedules.save(
                db,
                sid,
                schedules.Schedule(
                    KEY, {}, notice="123", title="공식 행사", events=None
                ),
            ),
            (0, 0),
        )
        apply(["20:00 (취소)"])
        self.assertEqual(
            db.execute(
                "select count(*) from calendar_event where schedule_notice='123' and status='REJECTED'"
            ).fetchone()[0],
            2,
        )
        db.execute("update store set edit_version=2 where id=%s", (store,))
        db.execute("delete from store_game where store_id=%s", (store,))
        schedules.save(db, official, registry)
        self.assertFalse(
            db.execute(
                "select exists(select from store_game where store_id=%s)", (store,)
            ).fetchone()[0]
        )
