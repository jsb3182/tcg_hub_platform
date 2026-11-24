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
