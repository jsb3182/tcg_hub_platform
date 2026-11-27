import os
import unittest
import uuid
from pathlib import Path

from tcg_worker.catalog_sources.onepiece import CARD_LIST, OPTCG, Index, edition
from tcg_worker.sync import catalog_product_key, is_numbered_printing, save_cards


PREFIX = "catalog:ONEPIECE:"
REGIONAL = "[OPK-01] 부스터 팩 ROMANCE DAWN"


def printing(code, number, product, name="몽키 D. 루피"):
    index = Index()
    index.add(number, "ko", edition(name, None, None, CARD_LIST), 0, code, product)
    return next(index.records())


@unittest.skipUnless(os.getenv("TCG_TEST_DSN"), "dedicated PostgreSQL required")
class OnePiecePackContinuity(unittest.TestCase):
    def test_v55_upgrade_and_repeated_regional_import(self):
        import psycopg
        from psycopg import sql

        migrations = Path(__file__).resolve().parents[2] / "backend/src/main/resources/db/migration"
        with psycopg.connect(os.environ["TCG_TEST_DSN"]) as db, db.transaction(force_rollback=True):
            schema = sql.Identifier("op_pack_" + uuid.uuid4().hex)
            db.execute(sql.SQL("CREATE SCHEMA {}").format(schema))
            db.execute(sql.SQL("SET LOCAL search_path TO {},public").format(schema))
            files = sorted(migrations.glob("V*.sql"), key=lambda f: int(f.name[1:].split("__")[0]))
            for migration in files:
                if int(migration.name[1:].split("__")[0]) < 56:
                    db.execute(migration.read_text("utf-8"))

            def pack(code, name, key):
                return db.execute("""
                    insert into pack(game_code,code,name,legacy_key) values('ONEPIECE',%s,%s,%s) returning id
                    """, (code, name, key)).fetchone()[0]

            def hashed(code):
                return catalog_product_key(PREFIX, (code, ""))

            def card(pack_id, sku, number, status="PUBLISHED"):
                return db.execute("""
                    insert into card(game_code,pack_id,name,number,legacy_key,status)
                    values('ONEPIECE',%s,'몽키 D. 루피',%s,%s,%s) returning id
                    """, (pack_id, number, PREFIX + sku + ":" + number, status)).fetchone()[0]

            op1 = pack("OP-01", "Romance Dawn", PREFIX + "OP-01")
            previous = pack("OP-01", REGIONAL, hashed("OP-01"))
            manual = pack("OP-01", REGIONAL, None)
            unrelated = pack("OP-01", "다른 제품", catalog_product_key(PREFIX, ("OP-01", "other product")))
            original_only = pack("ST-02", "Starter", PREFIX + "ST-02")
            hash_only = pack("EB-01", "Extra Booster", hashed("EB-01"))
            old_conflict = pack("OP-02", "Separate edits", PREFIX + "OP-02")
            hash_conflict = pack("OP-02", "Separate edits", hashed("OP-02"))
            # Conflicting editorial values must remain separately addressable.
            db.execute("update pack set release_date='2022-01-01' where id=%s", (old_conflict,))
            db.execute("update pack set release_date='2022-02-02' where id=%s", (hash_conflict,))
            db.execute("update pack set metadata='{\"localNote\":true}' where id=%s", (previous,))
            leader = card(previous, "OP-01", "OP01-003")
            pending = card(op1, "OP-01", "OP01-004", "PENDING")
            refused = card(hash_conflict, "OP-02", "OP02-001", "REJECTED")
            starter = card(original_only, "ST-02", "ST02-001")
            extra = card(hash_only, "EB-01", "OP01-003")
            variant = db.execute("insert into card_variant(card_id) values(%s) returning id", (leader,)).fetchone()[0]
            owner = db.execute("insert into app_user(email,password_hash) values('op@example.invalid','test') returning id").fetchone()[0]
            db.execute("insert into binder_card(owner_id,card_id,quantity) values(%s,%s,4)", (owner, leader))
            db.execute("insert into deck_rule(game_code,format,version) values('ONEPIECE','fixture',1)")
            db.execute("insert into deck_section_rule(game_code,format,rule_version,section) values('ONEPIECE','fixture',1,'main')")
            deck = db.execute("""
                insert into deck(owner_id,game_code,name,format) values(%s,'ONEPIECE','Test','fixture') returning id
                """, (owner,)).fetchone()[0]
            db.execute("""
                insert into deck_entry(deck_id,game_code,card_id,section,quantity,format,rule_version)
                values(%s,'ONEPIECE',%s,'main',2,'fixture',1)
                """, (deck, leader))
            selected = db.execute("""
                insert into product_release(game_code,product_key,region,name,release_date,source_url,manual,selected_pack_id)
                values('ONEPIECE','test:selected','KR','운영자 일정','2088-01-03','https://example.invalid',true,%s) returning id
                """, (previous,)).fetchone()[0]
            db.execute("""
                insert into product_release(game_code,product_key,region,name,release_date,source_url,catalog_code,catalog_name)
                values('ONEPIECE','test:regional','KR','국내 발매','2088-01-02','https://example.invalid','OP-01',%s)
                """, (REGIONAL,))
            # Shipped .13 added DON!! alongside collector-number printings; V56 kept these pairs visible.
            # Check each independent reason the source or editor might require both records to remain.
            don_cases = []
            for sku, source_url, kind, product in [
                    ("OP-03", OPTCG + "allDonCards/", "don", "OP-03"),
                    ("OP-04", "https://example.invalid/don", "don", "OP-04"),
                    ("OP-05", OPTCG + "allDonCards/", "leader", "OP-05"),
                    ("OP-06", OPTCG + "allDonCards/", "don", "OP-07"),
                    ("OP-07", OPTCG + "allDonCards/", "don", "OP-07")]:
                base = pack(sku, "Old package title", PREFIX + sku)
                hashed_pack = pack(sku, "Regional package title", hashed(sku))
                did = card(hashed_pack, sku, "DON:don_19")
                db.execute("""update card set source_url=%s, specs=jsonb_build_object('type',%s::text,'productCode',%s::text)
                              where id=%s""", (source_url, kind, product, did))
                if sku == "OP-07":
                    db.execute("update pack set release_label='manual A' where id=%s", (base,))
                    db.execute("update pack set release_label='manual B' where id=%s", (hashed_pack,))
                don_cases.append((sku, base, hashed_pack, did))
            db.execute(next(migrations.glob("V56__*.sql")).read_text("utf-8"))
            for _, _, hashed_pack, _ in don_cases:
                self.assertEqual(db.execute("select current_catalog_pack(%s)", (hashed_pack,)).fetchone(), (hashed_pack,))
            db.execute(next(migrations.glob("V57__*.sql")).read_text("utf-8"))
            for sku, base, hashed_pack, did in don_cases:
                target = base if sku == "OP-03" else hashed_pack
                self.assertEqual(db.execute("select current_catalog_pack(%s),pack_id from card where id=%s",
                                            (hashed_pack, did)).fetchone(), (target, target))
            source_id = db.execute("select id from feed_source where provider='CATALOG' and source_key='ONEPIECE'").fetchone()[0]
            source = {"game_code": "ONEPIECE", "id": source_id, "auto_publish": True}
            rows = [
                printing("OP-01", "OP01-003", "Renamed product"),
                printing("OP-01", "OP01-004", REGIONAL),
                printing("ST-02", "ST02-001", "지역별 덱"),
                printing("EB-01", "OP01-003", "Reprint"),
                printing("OP-02", "OP02-001", "New label"),
            ]
            for _ in range(2):
                self.assertEqual(save_cards(db, source, rows), 0)
                ids = [leader, pending, refused, starter, extra]
                self.assertEqual(db.execute("select id,pack_id,status from card where id=any(%s) order by id", (ids,)).fetchall(), [
                    (leader, op1, "PUBLISHED"), (pending, op1, "PENDING"), (refused, hash_conflict, "REJECTED"),
                    (starter, original_only, "PUBLISHED"), (extra, hash_only, "PUBLISHED"),
                ])
            self.assertEqual(db.execute("select current_catalog_pack(%s),current_catalog_pack(%s)", (previous, op1)).fetchone(), (op1, op1))
            visible = [op1, manual, unrelated, original_only, hash_only, old_conflict, hash_conflict]
            self.assertEqual(db.execute("select id from visible_catalog_pack where id=any(%s) order by id", (visible + [previous],)).fetchall(),
                             [(i,) for i in sorted(visible)])
            self.assertEqual(db.execute("select name from onepiece_pack_label where pack_id=%s order by name collate \"C\"", (op1,)).fetchall(),
                             [(n,) for n in sorted(["Romance Dawn", REGIONAL, "Renamed product"])])
            self.assertEqual(db.execute("select metadata from pack where id=%s", (op1,)).fetchone()[0]["localNote"], True)
            self.assertEqual(db.execute("select selected_pack_id,current_catalog_pack(selected_pack_id),version from product_release where id=%s",
                                        (selected,)).fetchone(), (previous, op1, 1))
            self.assertEqual(db.execute("select release_date::text from catalog_pack_date where pack_id=%s", (op1,)).fetchone(), ("2088-01-02",))
            self.assertEqual(db.execute("select id from card_variant where card_id=%s", (leader,)).fetchone(), (variant,))
            self.assertEqual(db.execute("select quantity from binder_card where owner_id=%s and card_id=%s", (owner, leader)).fetchone(), (4,))
            self.assertEqual(db.execute("select quantity from deck_entry where deck_id=%s and card_id=%s", (deck, leader)).fetchone(), (2,))

            promos = [printing("PROMO", "P-001", "행사 A"), printing("PROMO", "P-002", "행사 B")]
            self.assertEqual(save_cards(db, source, promos), 2)
            self.assertEqual(save_cards(db, source, reversed(promos)), 0)
            self.assertEqual(db.execute("select count(distinct pack_id) from card where legacy_key like 'catalog:ONEPIECE:PROMO:%'").fetchone(), (2,))
            self.assertEqual(db.execute("select onepiece_numbered_pack_key('OP-01'),onepiece_numbered_pack_key('PROMO')").fetchone(),
                             (hashed("OP-01"), None))

    def test_don_id_must_belong_to_the_source_and_product(self):
        card = {"external_id":"OP-01:DON:don_19", "number":"DON:don_19", "source_url":OPTCG + "allDonCards/",
                "specs":{"type":"don", "productCode":"OP-01"}}
        self.assertTrue(is_numbered_printing(card, "OP-01"))
        for patch in ({"external_id":"OP-02:DON:don_19"}, {"source_url":OPTCG + "allSetCards/"},
                      {"specs":{"type":"leader", "productCode":"OP-01"}}, {"specs":{"type":"don"}},
                      {"number":"DON:other_19", "external_id":"OP-01:DON:other_19"}):
            self.assertFalse(is_numbered_printing({**card, **patch}, "OP-01"))
        self.assertFalse(is_numbered_printing(card, "PROMO"))
