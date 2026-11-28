import json
import os
from pathlib import Path
import tempfile
import unittest
import uuid
from unittest.mock import Mock, patch
import zipfile

from tcg_worker.catalog_sources import weiss_art
from tcg_worker.catalog_sources.bulk import weiss
from tcg_worker.local_art import provider


class WeissReferences(unittest.TestCase):
    def test_deep_english_print_reference_not_downloadable(self):
        image = weiss_art.ORIGIN + "/wp/wp-content/images/cardimages/test/BP/test_001.png"
        card = dict(name="Card", code="T/W01-E001", expansion="Trial", image=image)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "archive.zip"
            with zipfile.ZipFile(path, "w") as z:
                z.writestr("repo/DB/T set.json", json.dumps([card]))
            http = Mock()
            http.get.return_value = path
            with patch("tcg_worker.catalog_sources.bulk.revision",return_value="b"*40):
                first, = weiss(http)
                again, = weiss(http)
        self.assertEqual(first, again)
        self.assertEqual(first["external_id"], "en:T/W01-E001")
        self.assertEqual(first["source_url"], "https://en.ws-tcg.com/cardlist/cardsearch/exec?cardno=T%2FW01-E001")
        self.assertNotIn("images",first["specs"])
        reference = first["specs"]["publisherArtwork"]["en"]
        self.assertIsNone(provider(reference["imageUrl"]))
        self.assertEqual(reference["imageUrl"],image)
        self.assertEqual(reference["printingNumber"],card["code"])
        self.assertEqual(reference["basis"],"MAINTAINER_PRINTING_REFERENCE")
        self.assertEqual(reference["cardUrl"],"https://en.ws-tcg.com/cardlist/?cardno=T%2FW01-E001")
        self.assertTrue(reference["sourceUrl"].endswith("b"*40+"/DB/T%20set.json"))

    def test_official_page_requires_number_title_product_and_single_english_art(self):
        c = dict(code="T/W01-E001",name="Example",expansion="Set one")
        image = "/wordpress/wp-content/images/cardimages/t/bp/example.png"
        raw = f"""<div class="p-cards__detail-wrapper-inner"><div class="p-cards__detail-textarea">
              <p class="number">{c['code']}</p><p class="ttl">{c['name']}</p></div>
              <div class="p-cards__detail-type"><dl><dt>Expansion</dt><dd>Set one</dd></dl></div>
              <div class="image"><img src="{image}"></div></div>""".encode()
        record = weiss_art.from_detail(c,raw,"2026-11-28")
        self.assertEqual(record["imageUrl"],weiss_art.ORIGIN+image)
        for altered in (raw.replace(b"E001",b"E001SP"),raw.replace(b"Example",b"Other"),raw.replace(b"Set one",b"Set two"),
                        raw.replace(b'<img ',b'<img src="/other.png"><img '),raw.replace(b'src="/wordpress',b'src="https://ws-tcg.com/wordpress')):
            self.assertIsNone(weiss_art.from_detail(c,altered,"2026-11-28"))

    def test_foreign_placeholder_unsafe_paths_and_ambiguous_images(self):
        image = weiss_art.ORIGIN+"/cardlist/cardimages/T_001.png"
        self.assertEqual(weiss_art.reference_image(image),image)
        for bad in ("https://ws-tcg.com/cardlist/cardimages/T_001.png",
                    weiss_art.ORIGIN+"/cardlist/cardimages/dc_w00_00.gif",
                    image+"?file=x",image+"#frag",image.replace("T_001","../T_001"),
                    image.replace("T_001","%2e%2e/T_001"),image.replace("/cardlist","/redirect")):
            self.assertIsNone(weiss_art.reference_image(bad))
        rows=[{"code":f"T/W01-E00{i}","name":"T","image":image} for i in (1,2)]
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp)/"cards.zip"
            with zipfile.ZipFile(archive,"w") as z:
                z.writestr("repo/DB/set.json",json.dumps(rows))
            with zipfile.ZipFile(archive) as z:
                ambiguous = weiss_art.conflicting_prints(z)
        self.assertEqual(ambiguous,{r["code"] for r in rows})
        for card in rows:
            self.assertNotIn("publisherArtwork",weiss_art.metadata(card,"a"*40,"set.json",ambiguous))

    def test_pinned_official_details_supersede_historical_file_only_for_exact_edition(self):
        c=dict(weiss_art.reviewed_pages()["AOT/S35-E002"])
        old=weiss_art.ORIGIN+"/cardlist/cardimages/WS_AOT_S35_E002RR.png"
        c["image"]=old
        observed=weiss_art.metadata(c,"a"*40,"AOT_S35.json",set())["publisherArtwork"]["en"]
        self.assertEqual(observed["basis"],"PUBLISHER_CARD_DETAIL")
        self.assertEqual(observed["imageUrl"],c["imageUrl"])
        self.assertNotEqual(observed["imageUrl"],old)
        self.assertEqual(weiss_art.metadata({**c,"expansion":"Other edition"},"a"*40,"AOT_S35.json",set())[
            "publisherArtwork"]["en"]["basis"],"MAINTAINER_PRINTING_REFERENCE")

    @unittest.skipUnless(os.getenv("TCG_TEST_DSN"), "dedicated PostgreSQL required")
    def test_catalog_update_preserves_print_ids_reviewed_text_and_uploaded_atlas(self):
        import psycopg
        from psycopg import sql
        from tcg_worker.local_art import discover
        from tcg_worker.sync import save_cards

        with psycopg.connect(os.environ["TCG_TEST_DSN"]) as db, db.transaction(force_rollback=True):
            schema = sql.Identifier("ws_refs_" + uuid.uuid4().hex)
            db.execute(sql.SQL("CREATE SCHEMA {}").format(schema))
            db.execute(sql.SQL("SET LOCAL search_path TO {},public").format(schema))
            migrations = Path(__file__).resolve().parents[2] / "backend/src/main/resources/db/migration"
            for path in sorted(migrations.glob("V*.sql"), key=lambda p:int(p.name[1:].split("__")[0])):
                db.execute(path.read_text("utf8"))
            archived = {"5HY/W83-E001":"/wp/wp-content/images/cardimages/5HY/BP/5HY_W83_E001.png",
                        "AOT/S35-E002":"/cardlist/cardimages/WS_AOT_S35_E002RR.png",
                        "HOL/W104-PE02":"/wp/wp-content/uploads/20230720095122/WS_HOL_W104_EP02PR-1.png"}
            rows = [{**r, "image": weiss_art.ORIGIN + archived[r["code"]]}
                    for r in weiss_art.reviewed_pages().values() if r["code"] in archived]
            with tempfile.TemporaryDirectory() as tmp:
                archive = Path(tmp)/"cards.zip"
                with zipfile.ZipFile(archive,"w") as z:
                    z.writestr("repo/DB/verified.json",json.dumps(rows))
                http = Mock()
                http.get.return_value=archive
                with patch("tcg_worker.catalog_sources.bulk.revision",return_value="c"*40):
                    current = list(weiss(http))
            source_id=db.execute("select id from feed_source where provider='CATALOG' and source_key='WEISS'").fetchone()[0]
            source={"id":source_id,"game_code":"WEISS","auto_publish":True}
            previous=[{**r,"specs":{"language":"en","images":{"en":raw["image"]}}} for r,raw in zip(current,rows)]
            self.assertEqual(save_cards(db,source,previous),len(archived))
            identity="select id,legacy_key,pack_id,number,source_url,status from card where game_code='WEISS' order by id"
            before=db.execute(identity).fetchall()
            cid=before[0][0]
            db.execute("""insert into card_translation(card_id,lang,name,effect,source_url,basis,version)
                          values(%s,'ko','검수명','검수 효과','https://example.invalid/owner','TRANSLATED_NAME',1)""",(cid,))
            sheet = db.execute("insert into image_sheet(storage_key,cell_width,cell_height) values(%s,240,336) returning id",
                               ("sheets/"+"a"*64+".webp",)).fetchone()[0]
            db.execute("update card_variant set sheet_id=%s,col_idx=2,row_idx=1 where card_id=%s",(sheet,cid))
            self.assertEqual(save_cards(db,source,current),0)
            self.assertEqual(save_cards(db,source,current),0)
            discover(db,"WEISS",96)
            self.assertEqual(db.execute(identity).fetchall(),before)
            self.assertEqual(db.execute("select count(*) from catalog_art_card").fetchone(),(0,))
            self.assertEqual(db.execute("select sheet_id,col_idx,row_idx from card_variant where card_id=%s",(cid,)).fetchone(),(sheet,2,1))
            self.assertEqual(db.execute("select name,effect,version from card_translation where card_id=%s",(cid,)).fetchone(),("검수명","검수 효과",1))
            for number,ref in db.execute("select number,specs->'publisherArtwork'->'en' from card where game_code='WEISS'"):
                self.assertEqual(ref["printingNumber"],number)
                self.assertEqual(ref["imageUrl"],weiss_art.reviewed_pages()[number]["imageUrl"])
