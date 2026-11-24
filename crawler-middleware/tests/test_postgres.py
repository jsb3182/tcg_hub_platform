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
        for migration in sorted(migrations.glob("V*.sql")):
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
            row = self.db.execute("SELECT c.name,c.status,v.sheet_id,v.col_idx,v.row_idx FROM card c JOIN card_variant v ON v.card_id=c.id WHERE c.id=%s", (cid,)).fetchone()
            self.assertEqual(row, ("revised", "REJECTED", sheet, 1, 2))
            item = Headline("post-1", "Title", "https://example.org/post", None)
            self.assertEqual(save_news(self.db, source, [item]), 1)
            self.db.execute("UPDATE feed_item SET status='REJECTED' WHERE source_id=%s", (sid,))
            self.assertEqual(save_news(self.db, source, [item]), 0)
            self.assertEqual(self.db.execute("SELECT status FROM feed_item WHERE source_id=%s", (sid,)).fetchone()[0], "REJECTED")

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

        with patch("tcg_worker.jobs.publish", interrupt_after_file), self.assertRaises(RuntimeError):
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

    @unittest.skipUnless(os.environ.get("TCG_TEST_LEGACY"), "set TCG_TEST_LEGACY to the original export")
    def test_catalog_import_and_repeat(self):
        from tcg_worker.legacy import import_catalog

        source = Path(os.environ["TCG_TEST_LEGACY"])
        for _ in range(2):
            stats = import_catalog(self.db, source, self.media)
            self.assertEqual((stats["packs"], stats["cards"], stats["sheets"]), (23, 994, 82))
        actual = self.db.execute(
            """SELECT count(*), count(*) FILTER (WHERE number IS NULL)
               FROM card WHERE game_code='YUGIOH'"""
        ).fetchone()
        self.assertEqual(actual, (994, 304))
        variants = self.db.execute(
            """SELECT count(*),count(sheet_id) FROM card_variant v JOIN card c ON v.card_id=c.id
               WHERE c.game_code='YUGIOH'"""
        ).fetchone()
        self.assertEqual(variants, (1044, 954))
        self.assertEqual(self.db.execute("SELECT count(*) FROM pack WHERE game_code='YUGIOH'").fetchone()[0], 23)
        keys = self.db.execute(
            """SELECT DISTINCT s.storage_key FROM image_sheet s JOIN card_variant v ON v.sheet_id=s.id
               JOIN card c ON c.id=v.card_id WHERE c.game_code='YUGIOH'"""
        )
        for (key,) in keys:
            self.assertTrue((self.media / key).is_file())
