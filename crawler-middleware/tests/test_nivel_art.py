import io
import os
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError

import psycopg
from bs4 import BeautifulSoup
from PIL import Image
from psycopg.types.json import Jsonb

from tcg_worker.catalog_sources.nivel import ART_ROOT, BOARD, board_art, matching_thumbnail
from tcg_worker.local_art import batch, discover


class NivelArtTests(unittest.TestCase):
    def test_board_uses_the_clicked_article_and_matches_its_thumbnail(self):
        full = ART_ROOT + "publisher-a.jpg"
        thumb = ART_ROOT + "thumb-publisher-a_225x315.jpg"

        def art(data, href, image=thumb):
            html = f'<li data-info="{data}"><div class="gall_img"><a href="{href}"><img src="{image}"></a></div></li>'
            return board_art(BeautifulSoup(html, "html.parser").li)

        signed = "publisher-a.jpg♬664"
        self.assertEqual(art(signed, signed), (full, thumb))
        self.assertEqual(art(signed, "publisher-a.jpg♬1291"), (thumb, None))
        self.assertEqual(art("other.jpg♬664", "other.jpg♬664"), (thumb, None))
        self.assertEqual(art("../publisher-a.jpg♬664", "../publisher-a.jpg♬664"), (thumb, None))
        self.assertIsNone(art(signed, signed, "https://other.test/" + thumb.split("/")[-1]))
        self.assertFalse(matching_thumbnail(full, ART_ROOT + "thumb-other_225x315.jpg"))
        self.assertFalse(matching_thumbnail(full, thumb + "?copy=1"))

    @unittest.skipUnless(os.environ.get("TCG_TEST_DSN"), "needs the PostgreSQL test schema")
    def test_original_first_thumbnail_fallback_and_grant_boundaries(self):
        full = ART_ROOT + "qa-a.jpg"
        thumb = ART_ROOT + "thumb-qa-a_225x315.jpg"
        spec = Jsonb({"images": {"ko": full}, "nivelThumbnail": thumb})
        seen = []
        image = io.BytesIO()
        Image.new("RGB", (90, 126), "green").save(image, "PNG")

        def fetch(url):
            seen.append(url)
            if url == full and seen.count(full) == 1:
                raise HTTPError(url, 404, "missing", {}, None)
            return image.getvalue()

        with psycopg.connect(os.environ["TCG_TEST_DSN"], autocommit=True) as db, tempfile.TemporaryDirectory() as tmp:
            for table in ("card", "catalog_art_file", "catalog_art_card", "catalog_art_scan", "catalog_art_host"):
                db.execute(f"CREATE TEMP TABLE {table} (LIKE public.{table} INCLUDING ALL)")
            source = db.execute("SELECT id FROM feed_source WHERE provider='CATALOG' AND source_key='NIVEL'").fetchone()[0]
            for cid, game, key, page in ((1, "NIVEL", "catalog:NIVEL:ko:664", "664"),
                                         (2, "NIVEL", "catalog:NIVEL:ko:665", "664"),
                                         (3, "POKEMON", "catalog:POKEMON:ko:666", "666")):
                db.execute("""INSERT INTO card(id,game_code,name,status,legacy_key,source_id,source_url,specs)
                              VALUES (%s,%s,'fixture','PUBLISHED',%s,%s,%s,%s)""",
                           (cid, game, key, source, BOARD + "&wr_id=" + page, spec))
            for game in ("NIVEL", "POKEMON"):
                discover(db, game, 50)
            grants = db.execute("""SELECT a.card_id FROM catalog_art_card a JOIN catalog_art_file f ON f.id=a.file_id
                                        WHERE f.source_url=%s ORDER BY 1""", (thumb,)).fetchall()
            self.assertEqual(grants, [(1,)])

            def run():
                return batch(db, Path(tmp), threading.Event(), games=("NIVEL",), scan=0,
                             fetch=fetch, policy=lambda url: 3)

            self.assertEqual(run(), 0)
            self.assertEqual(seen, [full])
            self.assertEqual(run(), 0)  # same-host delay is respected
            db.execute("UPDATE catalog_art_host SET next_attempt=now()")
            self.assertEqual(run(), 1)
            self.assertEqual(seen, [full, thumb])
            db.execute("UPDATE catalog_art_host SET next_attempt=now()")
            db.execute("UPDATE catalog_art_file SET next_attempt=now() WHERE source_url=%s", (full,))
            self.assertEqual(run(), 1)
            db.execute("UPDATE catalog_art_host SET next_attempt=now()")
            db.execute("UPDATE catalog_art_file SET next_attempt=now() WHERE source_url=%s", (thumb,))
            self.assertEqual(run(), 0)  # keep the cached small image without downloading it twice
            self.assertEqual(seen, [full, thumb, full])
            self.assertEqual(db.execute("SELECT count(*) FROM catalog_art_file WHERE storage_key IS NOT NULL").fetchone(), (2,))

            for ident, stem in ((710, "b"), (711, "c")):
                specs = Jsonb({"images": {"ko": ART_ROOT+stem+".jpg"},
                               "nivelThumbnail": ART_ROOT+"thumb-"+stem+"_225x315.jpg"})
                db.execute("""INSERT INTO card(id,game_code,name,status,legacy_key,source_id,source_url,specs)
                              VALUES (%s,'NIVEL','fixture','PUBLISHED',%s,%s,%s,%s)""",
                           (ident, f"catalog:NIVEL:ko:{ident}", source, BOARD+f"&wr_id={ident}", specs))
            discover(db, "NIVEL", 50)
            db.execute("""UPDATE catalog_art_file SET storage_key=(SELECT storage_key FROM catalog_art_file WHERE source_url=%s)
                          WHERE source_url=%s""", (thumb, ART_ROOT+"thumb-b_225x315.jpg"))
            db.execute("UPDATE catalog_art_file SET next_attempt=now()-interval '1 day' WHERE source_url=%s", (ART_ROOT+"b.jpg",))
            self.assertEqual(run(), 1)
            self.assertEqual(seen[-1], ART_ROOT+"c.jpg")
