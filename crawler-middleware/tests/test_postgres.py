import os
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from PIL import Image


@unittest.skipUnless(os.environ.get("TCG_TEST_DSN"), "set TCG_TEST_DSN to test PostgreSQL/PostGIS")
class DatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg
        from psycopg import sql

        cls.db = psycopg.connect(os.environ["TCG_TEST_DSN"], autocommit=True)
        cls.schema = sql.Identifier("test_tcg_" + uuid.uuid4().hex)
        cls.addClassCleanup(cls.db.close)
        cls.db.execute(sql.SQL("CREATE SCHEMA {}").format(cls.schema))
        cls.addClassCleanup(cls.db.execute, sql.SQL("DROP SCHEMA {} CASCADE").format(cls.schema))
        cls.db.execute(sql.SQL("SET search_path TO {},public").format(cls.schema))
        migrations = Path(__file__).resolve().parents[2] / "backend/src/main/resources/db/migration"
        for migration in sorted(migrations.glob("V*.sql"), key=lambda path: int(path.name[1:].split("__")[0])):
            cls.db.execute(migration.read_text(encoding="utf-8"))
            if migration.name == "V1__platform.sql":
                cls.db.execute(
                    """WITH owner AS (INSERT INTO app_user(email,password_hash) VALUES ('fixture@example.test','fixture') RETURNING id),
                            d AS (INSERT INTO deck(owner_id,game_code,name,format)
                                  SELECT id,'RIFTBOUND','fixture','local' FROM owner RETURNING id),
                            c AS (INSERT INTO card(game_code,name) VALUES ('RIFTBOUND','fixture') RETURNING id)
                       INSERT INTO deck_entry(deck_id,game_code,card_id,section,quantity)
                       SELECT d.id,'RIFTBOUND',c.id,'fixture-section',3 FROM d,c"""
                )

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.spool = Path(temp.name) / "private"
        self.media = Path(temp.name) / "media"
        self.input = Path(temp.name) / "test.png"
        Image.new("RGB", (300, 438), "red").save(self.input)

    def make_variant(self):
        card_id = self.db.execute(
            "INSERT INTO card(game_code,name,status) VALUES ('POKEMON','test','PUBLISHED') RETURNING id"
        ).fetchone()[0]
        return self.db.execute("INSERT INTO card_variant(card_id) VALUES (%s) RETURNING id", (card_id,)).fetchone()[0]

    def test_catalog_check_requires_published_source_cards_and_a_finished_import_for_each_game(self):
        from tcg_worker.__main__ import check_catalogs

        with self.db.transaction(force_rollback=True):
            self.db.execute("INSERT INTO card(game_code,name,status) VALUES ('YUGIOH','manual','PUBLISHED')")
            before = check_catalogs(self.db)
            self.assertEqual({row["game"] for row in before["catalogs"]},
                             {"YUGIOH", "POKEMON", "ONEPIECE", "WEISS", "NIVEL", "RIFTBOUND"})
            self.assertTrue(all(row["published"] == 0 for row in before["catalogs"]))
            self.assertFalse(before["initial_sync_complete"])
            self.db.execute("""
                INSERT INTO card(game_code,name,status,source_id)
                SELECT game_code,'imported', CASE WHEN game_code='NIVEL' THEN 'PENDING' ELSE 'PUBLISHED' END,id
                FROM feed_source WHERE provider='CATALOG'
            """)
            self.db.execute("UPDATE feed_source SET last_success_at=now() WHERE provider='CATALOG'")
            self.assertFalse(check_catalogs(self.db)["initial_sync_complete"])
            self.db.execute("UPDATE card SET status='PUBLISHED' WHERE game_code='NIVEL' AND source_id IS NOT NULL")
            self.db.execute("UPDATE feed_source SET last_success_at=NULL,state='RUNNING' WHERE provider='CATALOG' AND game_code='NIVEL'")
            self.assertFalse(check_catalogs(self.db)["initial_sync_complete"])
            self.db.execute("UPDATE feed_source SET last_success_at=now(),state='OK' WHERE provider='CATALOG' AND game_code='NIVEL'")
            complete = check_catalogs(self.db)
            self.assertTrue(complete["initial_sync_complete"])
            self.assertTrue(all(row["published"] == 1 and row["last_success_at"] for row in complete["catalogs"]))

    def test_sync_keeps_moderation_and_artwork_across_refresh(self):
        from tcg_worker.feeds import Headline
        from tcg_worker.sync import save_cards, save_news

        with self.db.transaction(force_rollback=True):
            sid = self.db.execute("SELECT id FROM feed_source WHERE provider='CATALOG' AND source_key='POKEMON'").fetchone()[0]
            source = {"id": sid, "game_code": "POKEMON", "auto_publish": False}
            record = {"external_id": "fixture", "source_url": "https://example.org/cards/1", "name": "first",
                      "pack_code": "test", "pack_name": "Test Pack"}
            self.assertEqual(save_cards(self.db, source, [record]), 1)
            sheet = self.db.execute("INSERT INTO image_sheet(storage_key,cell_width,cell_height) VALUES ('sync-fixture',10,10) RETURNING id").fetchone()[0]
            cid = self.db.execute("UPDATE card SET status='REJECTED' WHERE source_id=%s RETURNING id", (sid,)).fetchone()[0]
            self.db.execute("UPDATE card_variant SET sheet_id=%s,col_idx=1,row_idx=2 WHERE card_id=%s", (sheet, cid))
            self.assertEqual(save_cards(self.db, source, [{**record, "name": "revised"}]), 0)
            self.assertEqual(self.db.execute("SELECT edit_version FROM card WHERE id=%s", (cid,)).fetchone()[0], 2)
            self.assertEqual(save_cards(self.db, source, [{**record, "name": "revised"}]), 0)
            self.assertEqual(self.db.execute("SELECT edit_version FROM card WHERE id=%s", (cid,)).fetchone()[0], 2)
            row = self.db.execute("SELECT c.name,c.status,v.sheet_id,v.col_idx,v.row_idx FROM card c JOIN card_variant v ON v.card_id=c.id WHERE c.id=%s", (cid,)).fetchone()
            self.assertEqual(row, ("revised", "REJECTED", sheet, 1, 2))
            item = Headline("post-1", "Title", "https://example.org/post", None)
            self.assertEqual(save_news(self.db, source, [item]), 1)
            self.db.execute("UPDATE feed_item SET status='REJECTED' WHERE source_id=%s", (sid,))
            self.assertEqual(save_news(self.db, source, [item]), 0)
            self.assertEqual(self.db.execute("SELECT status FROM feed_item WHERE source_id=%s", (sid,)).fetchone()[0], "REJECTED")

    def test_onepiece_provenance_refresh_preserves_printing_and_variant_ids(self):
        from tcg_worker.catalog_sources.onepiece import Index, edition
        from tcg_worker.sync import save_cards

        index = Index()
        index.add("EB01-003", "en", edition("Card", "Effect", "en-art", "https://example.org/en"),
                  0, "EB-01", "Original")
        index.add("EB01-003", "ko", edition("카드", "효과", "ko-art", "https://example.org/ko"),
                  2, "OP-14", "Reprint")
        revised = list(index.records())
        old = [{**row, "specs": {k: v for k, v in row["specs"].items()
                                  if k not in {"productCode", "imageSources", "imageProducts"}}} for row in revised]
        with self.db.transaction(force_rollback=True):
            sid = self.db.execute("SELECT id FROM feed_source WHERE provider='CATALOG' AND game_code='ONEPIECE'").fetchone()[0]
            source = {"id": sid, "game_code": "ONEPIECE", "auto_publish": True}
            identity = """SELECT p.code,c.id,c.legacy_key,c.pack_id,v.id FROM card c
                          JOIN pack p ON p.id=c.pack_id JOIN card_variant v ON v.card_id=c.id
                          WHERE c.source_id=%s ORDER BY p.code"""
            self.assertEqual(save_cards(self.db, source, old), 2)
            ids = self.db.execute(identity, (sid,)).fetchall()
            for _ in range(2):
                self.assertEqual(save_cards(self.db, source, revised), 0)
                self.assertEqual(self.db.execute(identity, (sid,)).fetchall(), ids)
            provenance = self.db.execute("""SELECT specs->>'productCode',specs->'imageProducts'->>'ko',
                        specs->'imageSources'->>'ko',edit_version FROM card WHERE source_id=%s ORDER BY 1""",
                                         (sid,)).fetchall()
            self.assertEqual(provenance, [(code, "OP-14", "https://example.org/ko", 2) for code in ("EB-01", "OP-14")])

    def test_rifthunt_reimport_preserves_printings_and_personal_library(self):
        from unittest.mock import Mock
        from tcg_worker.catalog_sources.bulk import riftbound
        from tcg_worker.sync import save_cards

        rows = [{"name":"Fixture","set":"OGN","printing_id":str(uuid.uuid4()),"id":"legacy-" + suffix}
                for suffix in ("base","promo")]
        snapshot = {"sets":[{"id":"OGN","name":"Origins"}],"cards":rows}

        def linked():
            return self.db.execute("""
                SELECT c.id,c.legacy_key,c.pack_id,v.id,v.sheet_id,v.col_idx,v.row_idx,
                       b.owner_id,b.quantity,e.deck_id,e.section,e.quantity
                  FROM card c JOIN card_variant v ON v.card_id=c.id
                  JOIN binder_card b ON b.card_id=c.id JOIN deck_entry e ON e.card_id=c.id
                 WHERE c.source_id=%s ORDER BY c.id
            """, (source["id"],)).fetchall()

        with self.db.transaction(force_rollback=True), patch("tcg_worker.catalog_sources.bulk.document", return_value=snapshot):
            sid = self.db.execute("SELECT id FROM feed_source WHERE provider='CATALOG' AND game_code='RIFTBOUND'").fetchone()[0]
            source = {"id":sid,"game_code":"RIFTBOUND","auto_publish":True}
            self.assertEqual(save_cards(self.db, source, riftbound(Mock())), 2)
            owner = self.db.execute("SELECT id FROM app_user WHERE email='fixture@example.test'").fetchone()[0]
            deck = self.db.execute("""
                INSERT INTO deck(owner_id,game_code,name,format,rule_version)
                VALUES (%s,'RIFTBOUND','Fixture deck','CONSTRUCTED',2) RETURNING id
            """,(owner,)).fetchone()[0]
            sheet = self.db.execute("INSERT INTO image_sheet(storage_key,cell_width,cell_height) VALUES ('fixture-rift',30,44) RETURNING id").fetchone()[0]
            for col,row in enumerate(rows):
                card = self.db.execute("SELECT id FROM card WHERE legacy_key=%s", ("catalog:RIFTBOUND:en:"+row["printing_id"],)).fetchone()[0]
                self.db.execute("UPDATE card_variant SET sheet_id=%s,col_idx=%s,row_idx=0 WHERE card_id=%s",(sheet,col,card))
                self.db.execute("INSERT INTO binder_card(owner_id,card_id,quantity) VALUES (%s,%s,2)", (owner,card))
                self.db.execute("""
                    INSERT INTO deck_entry(deck_id,game_code,format,rule_version,card_id,section,quantity)
                    VALUES (%s,'RIFTBOUND','CONSTRUCTED',2,%s,'MAIN',1)
                """,(deck,card))
            before = linked()
            self.assertEqual(len(before), 2)
            for row in rows:
                del row["id"]
                row.update(riftboundId="ogn-001-298",num=1)
            self.assertEqual(save_cards(self.db, source, riftbound(Mock())), 0)
            self.assertEqual(linked(), before)
            actual = self.db.execute("SELECT number FROM card WHERE source_id=%s ORDER BY id", (sid,)).fetchall()
            self.assertEqual(actual, [("ogn-001-298",),("ogn-001-298",)])

    def test_reimport_preserves_manual_review_snapshot(self):
        from datetime import datetime, timezone
        from tcg_worker.feeds import Headline
        from tcg_worker.sync import save_news

        original = Headline("42", "Reviewed text", "https://example.org/reviewed", None, "Original summary")
        edited = Headline("42", "Edited upstream", "https://example.org/edited",
                          datetime(2026, 11, 1, tzinfo=timezone.utc), "Edited summary")
        with self.db.transaction(force_rollback=True):
            sid = self.db.execute("SELECT id FROM feed_source WHERE provider='DCINSIDE' AND source_key='tcggame'").fetchone()[0]
            source = {"id": sid, "auto_publish": False}
            self.assertEqual(save_news(self.db, source, [original]), 1)
            item = self.db.execute("SELECT id FROM feed_item WHERE source_id=%s", (sid,)).fetchone()[0]
            self.db.execute("INSERT INTO feed_item_translation(item_id,lang,title) VALUES (%s,'ko','검수한 번역')", (item,))
            reviewer = self.db.execute("SELECT id FROM app_user WHERE email='fixture@example.test'").fetchone()[0]
            for status in ("PENDING", "PUBLISHED", "REJECTED"):
                with self.subTest(status=status):
                    decision_by = None if status == "PENDING" else reviewer
                    self.db.execute("UPDATE feed_item SET status=%s,reviewer_id=%s WHERE id=%s", (status, decision_by, item))
                    self.assertEqual(save_news(self.db, source, [edited]), 0)
                    row = self.db.execute("""
                        SELECT i.status,i.reviewer_id,i.payload->>'title',i.payload->>'summary',i.source_url,
                               i.source_published_at,t.title FROM feed_item i
                        LEFT JOIN feed_item_translation t ON t.item_id=i.id AND t.lang='ko' WHERE i.id=%s
                    """, (item,)).fetchone()
                    self.assertEqual(row, (status, decision_by, original.title, original.summary,
                                           original.url, None, "검수한 번역"))

    def test_automatic_official_edits_refresh_only_unreviewed_published_text(self):
        from tcg_worker.feeds import Headline
        from tcg_worker.sync import save_news

        with self.db.transaction(force_rollback=True):
            sid = self.db.execute("SELECT id FROM feed_source WHERE provider='OFFICIAL_NEWS' AND source_key='weiss-en'").fetchone()[0]
            source = {"id": sid, "auto_publish": True}
            first = Headline("feed1", "Publisher headline", "https://example.org/original", None)
            with_excerpt = Headline("feed1", first.title, first.url, None, "Publisher excerpt")
            self.assertEqual(save_news(self.db, source, [first]), 1)
            item = self.db.execute("SELECT id FROM feed_item WHERE source_id=%s", (sid,)).fetchone()[0]
            self.db.execute("INSERT INTO feed_item_translation(item_id,lang,title) VALUES (%s,'ko','초기 번역')", (item,))
            self.assertEqual(save_news(self.db, source, [with_excerpt]), 0)
            row = self.db.execute("""
                SELECT payload->>'summary',translation_due_at IS NOT NULL,
                       EXISTS(SELECT 1 FROM feed_item_translation WHERE item_id=%s) FROM feed_item WHERE id=%s
            """, (item, item)).fetchone()
            self.assertEqual(row, (with_excerpt.summary, True, False))
            self.db.execute("""
                UPDATE feed_item SET reviewer_id=(SELECT id FROM app_user WHERE email='fixture@example.test') WHERE id=%s
            """, (item,))
            self.assertEqual(save_news(self.db, source, [first]), 0)
            self.assertEqual(self.db.execute("SELECT payload->>'summary' FROM feed_item WHERE id=%s", (item,)).fetchone(),
                             (with_excerpt.summary,))

    def test_reused_pack_code_keeps_product_and_card_ids(self):
        from tcg_worker.sync import save_cards

        def run(order, existing):
            with self.db.transaction(force_rollback=True):
                sid = self.db.execute("SELECT id FROM feed_source WHERE provider='CATALOG' AND game_code='WEISS'").fetchone()[0]
                source = {"id": sid, "game_code": "WEISS", "auto_publish": True}
                rows = [{"name": "Fixture " + str(i), "external_id": "fixture" + str(i), "pack_code": "WX",
                         "pack_name": name, "source_url": "https://example.org/test"}
                        for i, name in enumerate(["Trial Deck", "Booster Pack", "Booster  Pack", "Trial Deck"])]
                if existing:
                    pack_id = self.db.execute(
                        "INSERT INTO pack(game_code,name,code,legacy_key) VALUES ('WEISS','Trial Deck','WX','catalog:WEISS:WX') RETURNING id"
                    ).fetchone()[0]
                    card_id = self.db.execute(
                        """INSERT INTO card(game_code,name,legacy_key,pack_id) VALUES
                           ('WEISS','Fixture','catalog:WEISS:fixture1',%s) RETURNING id""", (pack_id,)
                    ).fetchone()[0]
                for index in order:
                    save_cards(self.db, source, [rows[index]])

                def snapshot():
                    return self.db.execute(
                        """SELECT c.id,p.id,p.legacy_key FROM card c JOIN pack p ON p.id=c.pack_id
                           WHERE c.source_id=%s ORDER BY c.legacy_key""", (sid,)
                    ).fetchall()

                first = snapshot()
                self.assertNotEqual(first[0][1], first[1][1])
                self.assertEqual(first[1][1], first[2][1])
                self.assertEqual(first[0][1], first[3][1])
                if existing:
                    self.assertEqual((first[0][1], first[1][0]), (pack_id, card_id))
                self.assertEqual(save_cards(self.db, source, reversed(rows)), 0)
                self.assertEqual(first, snapshot())
                return [r[2] for r in first]

        self.assertEqual(run(range(4), False), run(reversed(range(4)), False))
        run(range(4), True)

    def test_claim_honors_provider_floor_and_pause_for_manual_requests(self):
        from tcg_worker.sync import claim

        with self.db.transaction(force_rollback=True):
            self.db.execute("UPDATE feed_source SET enabled=false")
            sid = self.db.execute("""
                INSERT INTO feed_source(provider,source_key,requested_at,next_fetch_at,retry_after_at)
                VALUES ('X','fixture',now(),now(),now()+interval '1 hour') RETURNING id
            """).fetchone()[0]
            self.assertIsNone(claim(self.db, False))
            self.db.execute("UPDATE feed_source SET retry_after_at=NULL,enabled=false WHERE id=%s", (sid,))
            self.assertIsNone(claim(self.db, False))
            self.db.execute("UPDATE feed_source SET enabled=true WHERE id=%s", (sid,))
            row = claim(self.db, False)
            self.assertEqual(row["id"], sid)
            self.assertEqual(row["state"], "RUNNING")
            self.assertIsNone(row["requested_at"])
            self.assertIsNone(claim(self.db, False))

    def test_x_limit_survives_failed_page_and_applies_to_other_accounts(self):
        import psycopg
        from tcg_worker.feeds import FetchError
        from tcg_worker.sync import claim, fetch_x_with_limits

        schema = self.db.execute("SELECT current_schema()").fetchone()[0]
        self.addCleanup(self.db.execute, "DELETE FROM feed_provider_cooldown WHERE provider='X'")

        def interrupted_fetch(provider, key, cursor, *, on_x_limit):
            on_x_limit(180)
            on_x_limit(30)
            raise ValueError("fixture malformed after rate-limit headers")

        with psycopg.connect(os.environ["TCG_TEST_DSN"], autocommit=True,
                             options=f"-c search_path={schema},public") as worker:
            with patch("tcg_worker.sync.fetch_feed", side_effect=interrupted_fetch), self.assertRaises(ValueError):
                fetch_x_with_limits(worker, "first_account", {})
        with patch("tcg_worker.sync.fetch_feed") as fetch, self.assertRaises(FetchError) as raised:
            fetch_x_with_limits(self.db, "another_account", {})
        self.assertGreater(raised.exception.retry_after, 150)
        fetch.assert_not_called()
        with self.db.transaction(force_rollback=True):
            self.db.execute("UPDATE feed_source SET enabled=(provider='X'),next_fetch_at=now(),requested_at=now()")
            self.assertIsNone(claim(self.db, False))
            self.db.execute("UPDATE feed_source SET enabled=true WHERE provider='OFFICIAL_NEWS' AND policy_note IS NULL")
            self.assertEqual(claim(self.db, False)["provider"], "OFFICIAL_NEWS")
            self.db.execute("UPDATE feed_source SET enabled=false WHERE provider='OFFICIAL_NEWS'")
            self.db.execute("UPDATE feed_provider_cooldown SET retry_after_at=now()-interval '1 second'")
            self.assertEqual(claim(self.db, False)["provider"], "X")

    def test_news_page_and_checkpoint_roll_back_when_completion_fails(self):
        import threading
        import psycopg
        from psycopg.rows import dict_row
        from tcg_worker.feeds import FeedPage, Headline
        from tcg_worker.sync import sync_source

        schema = self.db.execute("SELECT current_schema()").fetchone()[0]
        with self.db.cursor(row_factory=dict_row) as cur:
            source = cur.execute("""
                INSERT INTO feed_source(provider,source_key,state,cursor_value)
                VALUES ('OFFICIAL_NEWS','atomic_check','RUNNING','{}') RETURNING *
            """).fetchone()
        self.addCleanup(self.db.execute, "DELETE FROM feed_source WHERE id=%s", (source["id"],))
        self.db.execute("""
            ALTER TABLE feed_source ADD CONSTRAINT fixture_finish_error
            CHECK (source_key <> 'atomic_check' OR state <> 'OK')
        """)
        self.addCleanup(self.db.execute, "ALTER TABLE feed_source DROP CONSTRAINT fixture_finish_error")
        item = Headline("item", "Sample", "https://example.org/post", None)
        with patch("tcg_worker.sync.connect", lambda: psycopg.connect(
                os.environ["TCG_TEST_DSN"], options=f"-c search_path={schema},public")), \
             patch("tcg_worker.sync.fetch_feed", return_value=FeedPage([item], {"page": 2}, more=True)):
            sync_source(source, threading.Event())
        row = self.db.execute("SELECT state,cursor_value,last_added FROM feed_source WHERE id=%s",
                              (source["id"],)).fetchone()
        self.assertEqual(row, ("ERROR", "{}", 0))
        self.assertEqual(self.db.execute("SELECT count(*) FROM feed_item WHERE source_id=%s",
                                         (source["id"],)).fetchone()[0], 0)

    def test_restart_recovers_interrupted_source_without_clearing_rate_limit(self):
        import threading
        import psycopg
        from tcg_worker.sync import run

        schema = self.db.execute("SELECT current_schema()").fetchone()[0]
        sid = self.db.execute("""
            INSERT INTO feed_source(provider,source_key,state,enabled,retry_after_at,cursor_value)
            VALUES ('X','restart_fixture','RUNNING',false,now()+interval '1 day','{"since":"100"}') RETURNING id
        """).fetchone()[0]
        self.db.execute("UPDATE worker_heartbeat SET restart_requested_at=now() WHERE id='tcg-worker'")
        before = self.db.execute("SELECT restart_count FROM worker_heartbeat WHERE id='tcg-worker'").fetchone()[0]
        with psycopg.connect(os.environ["TCG_TEST_DSN"], options=f"-c search_path={schema},public") as worker:
            run(worker, self.media, self.spool, threading.Event(), 1)
        self.assertEqual(self.db.execute("""
            SELECT restart_requested_at IS NULL,seen_at IS NOT NULL,restart_count
              FROM worker_heartbeat WHERE id='tcg-worker'
        """).fetchone(), (True, True, before + 1))
        self.assertEqual(self.db.execute("""
            SELECT state,enabled,retry_after_at>now(), cursor_value FROM feed_source WHERE id=%s
        """, (sid,)).fetchone(), ("IDLE", False, True, '{"since":"100"}'))

    def test_existing_deck_section_migrates_to_version_one(self):
        import psycopg

        entry = self.db.execute(
            """SELECT e.rule_version,e.section,e.quantity,r.max_cards FROM deck_entry e
               JOIN deck_section_rule r USING(game_code,format,rule_version,section)
               WHERE e.game_code='RIFTBOUND'"""
        ).fetchone()
        self.assertEqual(entry, (1, "fixture-section", 3, None))
        with self.assertRaises(psycopg.errors.ForeignKeyViolation):
            self.db.execute("UPDATE deck_entry SET section='undefined-section' WHERE game_code='RIFTBOUND'")

    def test_store_radius_uses_meters(self):
        self.db.execute(
            """INSERT INTO store(name,address,location) VALUES
               ('near','test',ST_SetSRID(ST_MakePoint(127.001,37.5),4326)),
               ('far','test',ST_SetSRID(ST_MakePoint(128.000,37.5),4326))"""
        )
        names = self.db.execute(
            "SELECT name FROM store WHERE ST_DWithin(location,ST_SetSRID(ST_MakePoint(127,37.5),4326)::geography,500)"
        ).fetchall()
        self.assertEqual(names, [("near",)])

    def test_batches_retries_and_partial_sheet(self):
        from tcg_worker.jobs import enqueue, process_once
        from tcg_worker.media import publish

        ids = [self.make_variant() for _ in range(13)]
        jobs = [enqueue(self.db, self.spool, v, self.input) for v in ids]
        self.assertEqual(enqueue(self.db, self.spool, ids[0], self.input), jobs[0])

        def interrupt_after_file(*args):
            publish(*args)
            raise RuntimeError("simulated interruption after rename")

        with patch("tcg_worker.atlases.publish", interrupt_after_file), self.assertRaises(RuntimeError):
            process_once(self.db, self.media, self.spool)
        count = self.db.execute("SELECT count(*) FROM media_job WHERE status='PENDING'").fetchone()[0]
        self.assertEqual(count, 13)
        for count in (12, 1, 0):
            self.assertEqual(process_once(self.db, self.media, self.spool), count)
        rows = self.db.execute(
            "SELECT sheet_id,col_idx,row_idx FROM card_variant WHERE id=ANY(%s) ORDER BY id", (ids,)
        ).fetchall()
        self.assertEqual(rows[0][1:], (0, 0))
        self.assertEqual(rows[11], (rows[0][0], 3, 2))
        self.assertEqual(rows[12][1:], (0, 0))
        self.assertNotEqual(rows[0][0], rows[12][0])
        self.assertEqual(len(list(self.media.glob("sheets/*.webp"))), 2)
        self.assertFalse(list(self.spool.iterdir()))

    def test_withdraw_repack_and_republish_shared_cells(self):
        from tcg_worker.jobs import enqueue, process_once

        def sheet(variant):
            return self.db.execute("""
                SELECT s.id,s.storage_key,s.retired,v.col_idx,v.row_idx,c.id
                  FROM image_sheet s JOIN card_variant v ON s.id=v.sheet_id JOIN card c ON c.id=v.card_id
                 WHERE v.id=%s""", (variant,)).fetchone()

        with self.db.transaction(force_rollback=True):
            first, second = self.make_variant(), self.make_variant()
            enqueue(self.db, self.spool, first, self.input)
            Image.new("RGB", (300, 438), "blue").save(self.input)
            enqueue(self.db, self.spool, second, self.input)
            process_once(self.db, self.media, self.spool)
            original = sheet(first)
            self.assertEqual(original[0], sheet(second)[0])
            self.db.execute("UPDATE card SET status='PENDING' WHERE id=%s", (original[5],))
            self.assertTrue(sheet(second)[2])
            process_once(self.db, self.media, self.spool)
            remaining = sheet(second)
            self.assertFalse(remaining[2])
            self.assertNotEqual(remaining[1], original[1])
            with Image.open(self.media / remaining[1]) as image:
                self.assertLess(max(image.getpixel((150, 219))[:3]), 40)
                self.assertGreater(image.getpixel((450, 219))[2], 220)
            self.assertTrue(sheet(first)[2])
            self.db.execute("UPDATE card SET status='PUBLISHED' WHERE id=%s", (original[5],))
            process_once(self.db, self.media, self.spool)
            restored = sheet(first)
            self.assertFalse(restored[2])
            self.assertNotEqual(restored[1], original[1])
            with Image.open(self.media / restored[1]) as image:
                self.assertGreater(image.getpixel((150, 219))[0], 220)
                self.assertLess(max(image.getpixel((450, 219))[:3]), 40)
            process_once(self.db, self.media, self.spool)
            self.assertFalse((self.media / original[1]).exists())

    def test_newest_queued_image_wins_without_leaving_superseded_pixels(self):
        from tcg_worker.jobs import enqueue, process_once
        with self.db.transaction(force_rollback=True):
            variant = self.make_variant()
            prior = enqueue(self.db, self.spool, variant, self.input)
            Image.new("RGB", (300, 438), "green").save(self.input)
            newest = enqueue(self.db, self.spool, variant, self.input)
            process_once(self.db, self.media, self.spool)
            states = self.db.execute("SELECT status FROM media_job WHERE id IN (%s,%s) ORDER BY id",
                                     (prior, newest)).fetchall()
            self.assertEqual(states, [("FAILED",), ("DONE",)])
            key = self.db.execute("""SELECT s.storage_key FROM card_variant v JOIN image_sheet s ON s.id=v.sheet_id
                                     WHERE v.id=%s AND v.col_idx=0 AND v.row_idx=0""", (variant,)).fetchone()[0]
            with Image.open(self.media / key) as image:
                self.assertGreater(image.getpixel((150, 219))[1], 110)
                self.assertLess(max(image.getpixel((450, 219))[:3]), 40)

    def test_missing_input_can_be_requeued(self):
        from tcg_worker.jobs import enqueue, process_once

        variant = self.make_variant()
        job = enqueue(self.db, self.spool, variant, self.input)
        next(self.spool.iterdir()).unlink()
        self.assertEqual(process_once(self.db, self.media, self.spool), 1)
        state = self.db.execute("SELECT status FROM media_job WHERE id=%s", (job,)).fetchone()[0]
        self.assertEqual(state, "FAILED")
        self.assertNotEqual(enqueue(self.db, self.spool, variant, self.input), job)
        self.assertEqual(process_once(self.db, self.media, self.spool), 1)

    def test_private_spool_reclaims_only_abandoned_images(self):
        from tcg_worker.jobs import enqueue, reclaim_orphans

        variant = self.make_variant()
        job = enqueue(self.db, self.spool, variant, self.input)
        self.addCleanup(self.db.execute, "DELETE FROM media_job WHERE id=%s", (job,))
        live = self.spool / self.db.execute("SELECT spool_key FROM media_job WHERE id=%s", (job,)).fetchone()[0]
        old = self.spool / (uuid.uuid4().hex + ".png")
        fresh = self.spool / (uuid.uuid4().hex + ".png")
        other = self.spool / "operator-file.png"
        interrupted = self.spool / ".tmp-1abcdef2"
        for path in (old, fresh, other, interrupted):
            path.touch()
        for path in (old, live, other, interrupted):
            os.utime(path, (1, 1))
        reclaim_orphans(self.db, self.spool)
        self.assertFalse(old.exists())
        self.assertFalse(interrupted.exists())
        self.assertTrue(live.exists())
        self.assertTrue(fresh.exists())
        self.assertTrue(other.exists())

    def test_unpublished_art_is_excluded(self):
        from tcg_worker.jobs import enqueue, process_once

        variant = self.make_variant()
        job = enqueue(self.db, self.spool, variant, self.input)
        self.db.execute(
            "UPDATE card SET status='PENDING' WHERE id=(SELECT card_id FROM card_variant WHERE id=%s)",
            (variant,),
        )
        with self.assertRaisesRegex(ValueError, "published"):
            enqueue(self.db, self.spool, variant, self.input)
        self.assertEqual(process_once(self.db, self.media, self.spool), 1)
        state = self.db.execute("SELECT status FROM media_job WHERE id=%s", (job,)).fetchone()[0]
        self.assertEqual(state, "FAILED")
        self.assertFalse(list(self.media.glob("sheets/*.webp")))

    def test_v15_retires_historical_partial_sheets_before_publication(self):
        from psycopg import sql

        migrations = Path(__file__).resolve().parents[2] / "backend/src/main/resources/db/migration"
        with self.db.transaction(force_rollback=True):
            schema = sql.Identifier("test_tcg_v15_" + uuid.uuid4().hex)
            self.db.execute(sql.SQL("CREATE SCHEMA {}").format(schema))
            self.db.execute(sql.SQL("SET LOCAL search_path TO {},public").format(schema))
            for number in range(1, 15):
                self.db.execute(next(migrations.glob(f"V{number}__*.sql")).read_text(encoding="utf-8"))
            for key, distinct in [("complete", 12), ("duplicate", 11), ("unused", 0)]:
                sheet = self.db.execute("""
                    INSERT INTO image_sheet(storage_key,cell_width,cell_height) VALUES (%s,10,10) RETURNING id
                """, (key,)).fetchone()[0]
                if distinct:
                    card = self.db.execute("""
                        INSERT INTO card(game_code,name,status) VALUES ('YUGIOH',%s,'PUBLISHED') RETURNING id
                    """, (key,)).fetchone()[0]
                    self.db.execute("""
                        INSERT INTO card_variant(card_id,position,sheet_id,col_idx,row_idx)
                        SELECT %s,i,%s,(i %% %s) %% 4,(i %% %s) / 4 FROM generate_series(0,11) i
                    """, (card, sheet, distinct, distinct))
            self.db.execute(next(migrations.glob("V15__*.sql")).read_text(encoding="utf-8"))
            rows = self.db.execute("""
                SELECT storage_key,retired,repack_at IS NOT NULL FROM image_sheet ORDER BY storage_key
            """).fetchall()
            self.assertEqual(rows, [("complete",False,False),("duplicate",True,True),("unused",True,True)])

    def test_partial_legacy_import_rebuilds_only_newly_needed_cells(self):
        import hashlib
        import json
        from tcg_worker.jobs import process_once
        from tcg_worker.legacy import import_catalog

        source = self.input.parent / "export"
        (source / "js").mkdir(parents=True)
        (source / "imgd").mkdir()
        pixels = Image.new("RGB", (160, 120), "red")
        pixels.paste("blue", (0, 0, 40, 40))
        sheet_path = source / "imgd/d1.webp"
        pixels.save(sheet_path, lossless=True)
        key = "sheets/" + hashlib.sha256(sheet_path.read_bytes()).hexdigest() + ".webp"
        pack = {"id":"incremental","name":"Fixture","cards":[{"xid":"a","n":"First","im":[1,0,0]}]}

        def load():
            (source / "js/app.js").write_text("var ITEMS = " + json.dumps([pack]) + ";", encoding="utf-8")
            import_catalog(self.db, source, self.media)

        def run():
            return process_once(self.db, self.media, self.spool)

        def current(name):
            return self.db.execute("""
                SELECT s.storage_key,s.retired,s.repack_at IS NOT NULL,v.id
                FROM card_variant v JOIN image_sheet s ON s.id=v.sheet_id JOIN card c ON c.id=v.card_id
                WHERE c.legacy_key=%s
            """, ("legacy:incremental:xid:" + name,)).fetchone()

        with self.db.transaction(force_rollback=True):
            self.db.execute("INSERT INTO verified_atlas_edition VALUES (%s,0,0,'ja'),(%s,1,0,'en')", (key,key))
            load()
            self.assertEqual(current("a")[:3], (key, True, True))
            self.assertTrue((self.media / key).is_file())
            self.assertEqual([run(),run(),run()], [1,1,0])
            first = current("a")
            self.assertFalse(first[1])
            labels = "SELECT col_idx,language FROM verified_atlas_edition WHERE storage_key=%s ORDER BY col_idx"
            self.assertEqual(self.db.execute(labels, (first[0],)).fetchall(), [(0, "ja")])
            with Image.open(self.media / first[0]) as clean:
                self.assertGreater(clean.getpixel((20,20))[2], 220)
                self.assertLess(max(clean.getpixel((60,20))[:3]), 40)
            load()
            self.assertFalse((self.media / key).exists())
            self.assertEqual(current("a"), first)
            self.assertEqual(run(), 0)

            pack["cards"].append({"xid":"b","n":"Second","im":[1,1,0]})
            load()
            self.assertEqual(current("b")[:3], (key, True, True))
            self.assertTrue((self.media / key).is_file())
            self.assertEqual([run(),run(),run()], [1,1,0])
            self.assertEqual(current("a"), first)
            second = current("b")
            self.assertFalse(second[1])
            self.assertEqual(self.db.execute(labels, (second[0],)).fetchall(), [(1, "en")])
            with Image.open(self.media / second[0]) as clean:
                self.assertLess(max(clean.getpixel((20,20))[:3]), 40)
                self.assertGreater(clean.getpixel((60,20))[0], 220)
            # An update into a drained retired target must wake the repacker too.
            self.db.execute("""
                UPDATE card_variant SET sheet_id=(SELECT id FROM image_sheet WHERE storage_key=%s) WHERE id=%s
            """, (key, second[3]))
            self.assertEqual(current("b")[:3], (key, True, True))
            load()
            self.assertTrue((self.media / key).is_file())

    @unittest.skipUnless(os.environ.get("TCG_TEST_LEGACY"), "set TCG_TEST_LEGACY to the original export")
    def test_catalog_import_and_repeat(self):
        from tcg_worker.legacy import import_catalog
        from tcg_worker.jobs import process_once

        source = Path(os.environ["TCG_TEST_LEGACY"])
        with self.db.transaction(force_rollback=True):
            stats = import_catalog(self.db, source, self.media)
            self.assertEqual((stats["packs"], stats["cards"], stats["sheets"]), (23, 994, 82))
            raw = self.db.execute("""
                SELECT s.storage_key FROM image_sheet s WHERE s.retired AND s.repack_at IS NOT NULL
                AND EXISTS (SELECT 1 FROM card_variant v JOIN card c ON c.id=v.card_id
                            WHERE v.sheet_id=s.id AND c.game_code='YUGIOH')
            """).fetchall()
            self.assertEqual(len(raw), 4)
            for _ in range(2 * len(raw)):
                self.assertEqual(process_once(self.db, self.media, self.spool), 1)
            self.assertEqual(import_catalog(self.db, source, self.media), stats)
            self.assertFalse(any((self.media / key).exists() for (key,) in raw))
            self.assertEqual(process_once(self.db, self.media, self.spool), 0)
            actual = self.db.execute("""
                SELECT count(*), count(*) FILTER (WHERE number IS NULL)
                FROM card WHERE game_code='YUGIOH'
            """).fetchone()
            self.assertEqual(actual, (994, 304))
            variants = self.db.execute("""
                SELECT count(*),count(sheet_id) FROM card_variant v JOIN card c ON v.card_id=c.id
                WHERE c.game_code='YUGIOH'
            """).fetchone()
            self.assertEqual(variants, (1044, 954))
            editions = self.db.execute("""
                SELECT e.language,count(DISTINCT c.id),count(DISTINCT (s.storage_key,v.col_idx,v.row_idx))
                FROM card c JOIN card_variant v ON v.card_id=c.id JOIN image_sheet s ON s.id=v.sheet_id
                LEFT JOIN verified_atlas_edition e USING (storage_key,col_idx,row_idx)
                WHERE c.status='PUBLISHED' AND c.legacy_key LIKE 'legacy:%' AND NOT s.retired
                GROUP BY e.language ORDER BY e.language NULLS LAST
            """).fetchall()
            self.assertEqual(editions, [("en",57,57), ("ja",846,892), (None,1,1)])
            self.assertEqual(self.db.execute("SELECT count(*) FROM pack WHERE game_code='YUGIOH'").fetchone()[0], 23)
            keys = self.db.execute("""
                SELECT DISTINCT s.storage_key,s.retired FROM image_sheet s JOIN card_variant v ON v.sheet_id=s.id
                JOIN card c ON c.id=v.card_id WHERE c.game_code='YUGIOH'
            """)
            for key, retired in keys:
                self.assertFalse(retired)
                self.assertTrue((self.media / key).is_file())
