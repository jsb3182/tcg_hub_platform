import io
import json
import os
import tarfile
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import Mock

import psycopg
from psycopg import sql

from tcg_worker.catalog_sources.card_names import ygo_names
from tcg_worker.legacy_editions import LegacyEditions


REVISION = "a" * 40
KEY = ("PK-JP001", "魔法使い")


def write_archive(path, cards):
    with tarfile.open(path, "w:gz") as bundle:
        for filename, card in cards:
            raw = json.dumps(card).encode()
            header = tarfile.TarInfo("repo/data/cards/" + filename)
            header.size = len(raw)
            bundle.addfile(header, io.BytesIO(raw))


def publisher_card():
    return {"konami_id": 101, "name": {"ja":"<ruby>魔法<rt>まほう</rt></ruby>使い","en":"Mage","ko":"마법사"},
            "text": {"ja":"効果","en":"Unofficial text","ko":"효과"}, "is_translation_unofficial":{"text":{"en":True}},
            "sets":{"ja":[{"set_number":KEY[0]}], "en":[{"set_number":"PK-EN001"}]}}


def english_card(name="English prize", number="WCPS-EN401", cid=None):
    return {"id":42,"name":name,"desc":"Printed effect","card_sets":[{"set_code":number}],
            "misc_info":[{"konami_id":cid}],"ygoprodeck_url":"https://ygoprodeck.com/card/prize-42"}


class LegacyEditionSourcesTest(unittest.TestCase):
    def test_exact_regional_pair_and_verified_fields_survive_cache_hit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "archive"
            alternate = publisher_card()
            alternate["sets"] = {"ja":[{"set_number":"ALT-JP002"}]}
            write_archive(archive, [("01.json", publisher_card()), ("02.json", alternate)])
            http = Mock(root=root)
            http.get.return_value = archive
            for run in range(2):
                with self.subTest(run=run):
                    candidates = LegacyEditions([KEY, ("ALT-JP002", KEY[1]), (KEY[0],"Mage"),
                                                 (KEY[0],"魔法"), ("OTHER",KEY[1])])
                    ygo_names(http, lambda *_: REVISION, candidates)
                    self.assertTrue(candidates.yaml_complete)
                    self.assertEqual({KEY, ("ALT-JP002",KEY[1])}, set(candidates.matches))
                    evidence = candidates.matches[KEY][1]
                    self.assertTrue(evidence["source_url"].endswith("/01.json"))
                    self.assertEqual({"ja":KEY[1],"en":"Mage","ko":"마법사"}, evidence["names"])
                    self.assertEqual({"ja":"効果","ko":"효과"}, evidence["texts"])
                    self.assertNotIn("images", evidence)
            self.assertEqual(http.get.call_count, 1)
            previous = LegacyEditions([KEY])
            still_usable = ygo_names(http, Mock(side_effect=OSError("offline")), previous)
            self.assertIn("101", still_usable)
            self.assertFalse(previous.yaml_complete)

    def test_existing_or_unknown_catalog_cannot_emit_english_only_updates_after_source_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            http = Mock(root=root)
            for version in ("new", "v2"):
                with self.subTest(version=version):
                    if version == "v2":
                        (root / ".ygo-printed-editions-v2.json").write_text(
                            json.dumps({"revision": REVISION, "names":{"101":{"names":{"ja":KEY[1]}}}}))
                    matches = LegacyEditions([KEY])
                    with self.assertRaises(OSError):
                        ygo_names(http, Mock(side_effect=OSError("offline")), matches)
                    self.assertFalse(matches.yaml_complete)
                    http.get.assert_not_called()

    def test_explicitly_empty_catalog_can_bootstrap_english_without_reconciling_legacy(self):
        with tempfile.TemporaryDirectory() as tmp:
            matches = LegacyEditions([KEY], allow_english_bootstrap=True)
            self.assertEqual({}, ygo_names(Mock(root=Path(tmp)), Mock(side_effect=OSError("offline")), matches))
            self.assertFalse(matches.yaml_complete)

    def test_ambiguous_ids_and_unofficial_name_do_not_identify_a_printing(self):
        other = publisher_card()
        other.update(konami_id=202, sets={"ja":[{"set_number":KEY[0]}], "en":[{"set_number":"PK-EN008"}]},
                     is_translation_unofficial={"name":{"en":True}})
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_archive(root/"fixture", [("01.json",publisher_card()),("02.json",other)])
            http = Mock(root=root)
            http.get.return_value = root/"fixture"
            matches = LegacyEditions([KEY, ("PK-EN008","Mage")])
            ygo_names(http, lambda *_: REVISION, matches)
            self.assertEqual({}, matches.matches)
            self.assertEqual({KEY}, matches.conflicts)

    def test_only_confirmed_english_ygoprodeck_prize_fields_are_used(self):
        correct = ("WCPS-EN401","English prize")
        matches = LegacyEditions([correct, ("WCPS-JP401","English prize")])
        matches.observe_ygopro(english_card())
        matches.observe_ygopro(english_card(number="WCPS-JP401"))
        matches.observe_ygopro(english_card(name="A different prize"))
        self.assertEqual({correct}, set(matches.matches))
        row = matches.matches[correct][1]
        self.assertIsNone(row["konami_id"])
        self.assertEqual({"en":"English prize"}, row["names"])
        self.assertEqual({"en":"Printed effect"}, row["texts"])
        matches.observe_ygopro(english_card(cid=903))
        self.assertEqual({}, matches.matches)


@unittest.skipUnless(os.environ.get("TCG_TEST_DSN"), "set TCG_TEST_DSN for a disposable PostgreSQL instance")
class LegacyEditionDatabaseTest(unittest.TestCase):
    def test_reconcile_preserves_imported_and_operator_data_and_retracts_old_evidence(self):
        with psycopg.connect(os.environ["TCG_TEST_DSN"]) as db, db.transaction(force_rollback=True):
            schema = sql.Identifier("evidence_"+uuid.uuid4().hex)
            db.execute(sql.SQL("create schema {}").format(schema))
            db.execute(sql.SQL("set local search_path to {}").format(schema))
            db.execute("create table card(id bigint primary key,legacy_key text,game_code text,number text,"
                       "original_name text,specs jsonb,name text,effect text,source_id bigint)")
            migration = (Path(__file__).resolve().parents[2] / "backend/src/main/resources/db/migration"
                         / "V26__legacy_card_editions.sql")
            db.execute(migration.read_text("utf-8"))
            self.assertTrue(LegacyEditions.from_database(db, 7).allow_english_bootstrap)
            for id_, key in ((1, "legacy:pack:row:0"), (2, "catalog:YUGIOH:en:42"), (3, None)):
                db.execute("insert into card values(%s,%s,'YUGIOH','WCPS-EN401','English prize',"
                           """'{"names":{"ko":"운영자 입력"}}','원본','효과')""", (id_, key))
            snapshot = LegacyEditions.from_database(db, 7)
            self.assertFalse(snapshot.allow_english_bootstrap)
            snapshot.observe_yaml(REVISION, {})
            snapshot.observe_ygopro(english_card())
            snapshot.reconcile(db)
            initial = db.execute("select ctid,card_id,texts->>'en' from legacy_card_edition").fetchall()
            self.assertEqual([(1, "Printed effect")], [r[1:] for r in initial])
            snapshot.reconcile(db)
            self.assertEqual(initial, db.execute("select ctid,card_id,texts->>'en' from legacy_card_edition").fetchall())
            corrected = LegacyEditions.from_database(db)
            corrected.observe_ygopro(dict(english_card(), desc="Corrected effect"))
            corrected.reconcile(db)
            self.assertEqual("Printed effect", db.execute("select texts->>'en' from legacy_card_edition").fetchone()[0])
            corrected.observe_yaml(REVISION, {})
            corrected.reconcile(db)
            self.assertEqual("Corrected effect", db.execute("select texts->>'en' from legacy_card_edition").fetchone()[0])
            absent = LegacyEditions.from_database(db)
            absent.observe_yaml("b"*40, {})
            absent.reconcile(db)
            self.assertEqual(0, db.execute("select count(*) from legacy_card_edition").fetchone()[0])
            correct_base = db.execute("select name,effect,specs->'names'->>'ko' from card where id=1").fetchone()
            self.assertEqual(("원본","효과","운영자 입력"), correct_base)
