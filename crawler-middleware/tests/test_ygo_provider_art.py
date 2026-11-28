import hashlib
import io
import os
from pathlib import Path
import tempfile
import threading
import unittest
import uuid
import zipfile

import psycopg
from psycopg import sql
from PIL import Image

from tcg_worker import local_art
from tcg_worker.ygo_representative import import_bundle


@unittest.skipUnless(os.getenv("TCG_TEST_DSN"), "requires a migrated disposable PostgreSQL database")
class ProviderReferenceTests(unittest.TestCase):
    def test_cache_once_hash_guard_and_offline_replay(self):
        output = io.BytesIO()
        Image.new("RGB", (176, 256), "teal").save(output, "JPEG")
        jpg = output.getvalue()
        sha = hashlib.sha256(jpg).hexdigest()
        url = "https://images.ygoprodeck.com/images/cards_small/904186.jpg"
        with tempfile.TemporaryDirectory() as directory, psycopg.connect(os.environ["TCG_TEST_DSN"]) as db:
            with db.transaction(force_rollback=True):
                schema = sql.Identifier("test_ygo_ref_" + uuid.uuid4().hex)
                db.execute(sql.SQL("create schema {}").format(schema))
                db.execute(sql.SQL("set local search_path to {},public").format(schema))
                migrations = Path(__file__).resolve().parents[2]/"backend/src/main/resources/db/migration"
                for migration in sorted(migrations.glob("V*.sql"),key=lambda f:int(f.name[1:].split("__")[0])):
                    db.execute(migration.read_text("utf8"))
                media = Path(directory)
                db.execute("update yugioh_provider_art set source_sha256=%s where source_url=%s", (sha, url))
                db.execute("update collection_control set crawler_enabled=true,scheduler_enabled=true")
                db.execute("update feed_source set enabled=true,policy_note=null where provider='CATALOG' and source_key='YUGIOH'")
                card = db.execute("""insert into card(game_code,name,original_name,number,legacy_key,specs,status,source_id,source_url)
                    select 'YUGIOH',p.original_name,p.original_name,p.printing_number,p.legacy_key,
                           jsonb_build_object('passcode',p.provider_card_id,'representativeArt',a.source_url),
                           'PUBLISHED',s.id,a.card_url
                      from yugioh_provider_printing p join yugioh_provider_art a using(provider_card_id)
                      join feed_source s on s.provider='CATALOG' and s.source_key='YUGIOH'
                     where p.provider_card_id='904186' and p.printing_number='OP09-PT026' returning id""").fetchone()[0]
                unrelated = db.execute("""insert into card(game_code,name,specs,status) values('POKEMON','wrong catalog',
                    jsonb_build_object('images',jsonb_build_object('en',%s::text)),'PUBLISHED') returning id""", (url,)).fetchone()[0]
                db.execute("delete from catalog_art_scan where game_code in ('YUGIOH','POKEMON')")
                local_art.discover(db, "YUGIOH", 200)
                local_art.discover(db, "POKEMON", 200)
                self.assertEqual(db.execute("select card_id from catalog_art_card a join catalog_art_file f on f.id=a.file_id where f.source_url=%s", (url,)).fetchall(), [(card,)])
                self.assertNotEqual(card, unrelated)
                db.execute("update catalog_art_file set next_attempt='infinity' where source_url<>%s", (url,))
                db.execute("delete from catalog_art_host where hostname=%s", (local_art.YGO_PROVIDER,))
                def fetch(asked):
                    self.assertEqual(asked, url)
                    return b"substituted bytes"
                stop = threading.Event()
                self.assertEqual(local_art.batch(db, media, stop, ("YUGIOH",), 0, fetch, lambda _:3), 0)
                self.assertEqual(db.execute("select storage_key,next_attempt='infinity' from catalog_art_file where source_url=%s", (url,)).fetchone(), (None, True))
                archive = media / "verified.zip"
                with zipfile.ZipFile(archive, "w") as z:
                    z.writestr("904186.jpg", jpg)
                bundle_sha = hashlib.sha256(archive.read_bytes()).hexdigest()
                first = import_bundle(db, media, archive, bundle_sha)
                second = import_bundle(db, media, archive, bundle_sha)
                self.assertEqual((first["matched"], first["cached"], second["cached"], second["newLinks"]), (1, 1, 0, 0))
                stored = db.execute("select storage_key,source_sha256,next_attempt='infinity' from catalog_art_file where source_url=%s",(url,)).fetchone()
                self.assertEqual(stored[1:], (sha,True))
                self.assertEqual(hashlib.sha256((media/stored[0]).read_bytes()).hexdigest(), Path(stored[0]).stem)
                db.execute("update card set specs=specs-'representativeArt' where id=%s", (card,))
                self.assertEqual(db.execute("select count(*) from catalog_art_card where card_id=%s", (card,)).fetchone(), (0,))
                self.assertEqual(import_bundle(db, media, archive, bundle_sha)["matched"], 0)
