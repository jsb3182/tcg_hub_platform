import os
import unittest
import uuid
from pathlib import Path

from tcg_worker.catalog_sources.nivel import BOARD, parse_detail, product_code
from tcg_worker.sync import save_cards


STARTER = "이터널 리턴 니벨아레나 스타터 덱 ST08 <애니버서리>"
BOOSTER = "이터널 리턴 니벨아레나 스페셜 부스터 팩 2026 SB02"


def charlotte(article, product):
    return parse_detail(
        f"<h2 id='subject'>타락의 유열 샬럿</h3><h2 id='type'>ST08-014 / 유닛 / 화염</h3>"
        f"<td class='h3'>제품명</td><td>{product}</td>", str(article))


class NivelProducts(unittest.TestCase):
    def test_reprint_keeps_collector_number_and_uses_its_own_product(self):
        first, second = charlotte(664, STARTER), charlotte(1291, BOOSTER)
        self.assertEqual([c["pack_code"] for c in (first, second)], ["ST08", "SB02"])
        self.assertEqual(first["number"], second["number"])
        self.assertEqual(second["source_url"], BOARD + "&wr_id=1291")
        self.assertEqual(second["specs"]["productName"], BOOSTER)

    def test_merchandise_and_promo_ranges_have_no_single_set_code(self):
        for text in ("레벨업리그 특전 카드", "니벨아레나 덱 ST12-14 프로모션 카드",
                     "ST04, ST05 프로모션 카드", "부스터 팩 BT01 프로모션 카드", "XXST08 덱"):
            self.assertIsNone(product_code(text))
        self.assertEqual(product_code("에픽세븐 니벨아레나 프로모션 팩 2026 PR01"), "PR01")
        with self.assertRaisesRegex(ValueError, "Missing Nivel product"):
            charlotte(664, "")

    @unittest.skipUnless(os.getenv("TCG_TEST_DSN"), "dedicated PostgreSQL required")
    def test_upgrade_and_replay_preserve_member_and_calendar_links(self):
        import psycopg
        from psycopg import sql

        path = Path(__file__).resolve().parents[2] / "backend/src/main/resources/db/migration"
        # All changes, including the isolated schema, are rolled back.
        with psycopg.connect(os.environ["TCG_TEST_DSN"]) as db, db.transaction(force_rollback=True):
            schema = sql.Identifier("nivel_" + uuid.uuid4().hex)
            db.execute(sql.SQL("CREATE SCHEMA {}").format(schema))
            db.execute(sql.SQL("SET LOCAL search_path TO {},public").format(schema))
            for migration in sorted(path.glob("V*.sql"), key=lambda f: int(f.name[1:].split("__")[0])):
                if int(migration.name[1:].split("__")[0]) < 54:
                    db.execute(migration.read_text("utf-8"))
            sid = db.execute("select id from feed_source where provider='CATALOG' and source_key='NIVEL'").fetchone()[0]
            source = {"game_code":"NIVEL", "id":sid, "auto_publish":True}
            def pack(code, name, key):
                return db.execute("insert into pack(game_code,code,name,legacy_key) values('NIVEL',%s,%s,%s) returning id",
                                  (code,name,key)).fetchone()[0]
            starter = pack("ST08", STARTER, "catalog:NIVEL:ST08")
            booster = pack("SB02", BOOSTER, "catalog:NIVEL:SB02")
            old = pack("ST08", BOOSTER, "catalog:NIVEL:edition:old")
            manual = pack("ST08", BOOSTER, None)
            records = [charlotte(664, STARTER), charlotte(1291, BOOSTER)]
            card_ids = []
            for row in records:
                card_ids.append(db.execute("""
                    insert into card(game_code,pack_id,name,number,legacy_key,source_id,source_url)
                    values('NIVEL',%s,%s,%s,%s,%s,%s) returning id
                    """, (starter,row["name"],row["number"],"catalog:NIVEL:"+row["external_id"],sid,row["source_url"])).fetchone()[0])
            cid = card_ids[1]
            variant = db.execute("insert into card_variant(card_id) values(%s) returning id",(cid,)).fetchone()[0]
            owner = db.execute("insert into app_user(email,password_hash) values('nivel@example.invalid','fixture') returning id").fetchone()[0]
            db.execute("insert into binder_card(owner_id,card_id,quantity) values(%s,%s,4)",(owner,cid))
            db.execute("insert into deck_rule(game_code,format,version) values('NIVEL','fixture',1)")
            db.execute("insert into deck_section_rule(game_code,format,rule_version,section) values('NIVEL','fixture',1,'main')")
            deck = db.execute("insert into deck(owner_id,game_code,name,format) values(%s,'NIVEL','QA','fixture') returning id",(owner,)).fetchone()[0]
            db.execute("insert into deck_entry(deck_id,game_code,card_id,section,quantity,format,rule_version) values(%s,'NIVEL',%s,'main',2,'fixture',1)",(deck,cid))
            event = db.execute("""
                insert into product_release(game_code,product_key,region,name,release_date,source_url,manual,selected_pack_id)
                values('NIVEL','fixture:manual','KR','운영자 일정','2026-01-25','https://example.invalid',true,%s) returning id
                """,(old,)).fetchone()[0]
            db.execute(next(path.glob("V54__*.sql")).read_text("utf-8"))
            for _ in range(2):
                self.assertEqual(save_cards(db, source, records), 0)
                actual = db.execute("select id,pack_id from card where id=any(%s) order by id",(card_ids,)).fetchall()
                self.assertEqual(actual,[(card_ids[0],starter),(cid,booster)])
            self.assertEqual(db.execute("select id from card_variant where card_id=%s",(cid,)).fetchone(),(variant,))
            self.assertEqual(db.execute("select quantity from binder_card where owner_id=%s and card_id=%s",(owner,cid)).fetchone(),(4,))
            self.assertEqual(db.execute("select quantity from deck_entry where deck_id=%s and card_id=%s",(deck,cid)).fetchone(),(2,))
            self.assertEqual(db.execute("select selected_pack_id,current_catalog_pack(selected_pack_id),version from product_release where id=%s",(event,)).fetchone(),(old,booster,1))
            self.assertEqual(db.execute("select release_date::text from catalog_pack_date where pack_id=%s",(booster,)).fetchone(),("2026-01-25",))
            self.assertEqual(db.execute("select id from visible_catalog_pack where id in (%s,%s) order by id",(manual,old)).fetchall(),[(manual,)])
