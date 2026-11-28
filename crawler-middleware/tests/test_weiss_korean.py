import gzip
import hashlib
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import Mock

from tcg_worker.catalog_sources.weiss_korean import complete_effect, draft_line, language_metadata, source_effect
from tcg_worker.weiss_readings import eligible, translated_fields, memory_key, memory_revision, VERSION
from tcg_worker.weiss_memory import import_memory, prepare_gpu


class WeissKoreanTests(TestCase):
    def test_related_name_requires_english_print_title_and_product(self):
        printed = {"code":"NIK/S117-E010","name":"Proceeding With the Plan, Rapi",
                   "expansion":"Booster Pack GODDESS OF VICTORY: NIKKE","side":"S",
                   "trigger":["SOUL"],"attributes":["NIKKE","Counters"]}
        result=language_metadata(printed)
        self.assertEqual(result["names"],{"ko":"작전 수행 라피"})
        self.assertEqual(result["nameBasis"],{"ko":"RELATED_PRINTING"})
        self.assertEqual(result["regionalFacts"]["ko"],{"side":"슈발츠","triggers":["소울"],"traits":["니케","카운터스"]})
        self.assertIn(result["relatedNamePrinting"]["ko"]["number"],{"NIK/S117-010S","NIK/S117-010SP"})
        for changes in ({"name":"Other"},{"expansion":"Promo"},{"code":"NIK/S117-E010SP"},{"code":"NIK/S117-E087"}):
            self.assertNotIn("names",language_metadata(printed | changes))
        self.assertNotIn("triggers",language_metadata(printed|{"trigger":["SOUL","BLUE"]})["regionalFacts"]["ko"])
        self.assertNotIn("traits",language_metadata(printed|{"attributes":["NIKKE","???"]})["regionalFacts"]["ko"])

    def test_complete_price_cost_timing_and_unknown_clause(self):
        line="【CONT】 All of your characters get +1000 power and +1 soul."
        gate="(【GATE】: When this card triggers, you may choose 1 climax in your waiting room, and return it to your hand)"
        self.assertEqual(complete_effect(line+"\n"+gate).count("\n"),1)
        self.assertIsNone(complete_effect(line+"\nIf another card has X, cancel this effect."))
        self.assertIsNone(complete_effect(line+" except for your center stage."))
        backup="【ACT】 【COUNTER】 Backup 2500, Level 2 [(1) Put this card from your hand into your waiting room] (Choose 1 of your characters that is being frontal attacked, and that character gets +2500 power until end of turn)"
        self.assertIn("[(1)",complete_effect(backup))
        self.assertIsNone(complete_effect(backup.replace("+2500","+3000")))
        self.assertIsNone(source_effect(["-"]))
        self.assertIsNone(source_effect([" "]))
        self.assertEqual(source_effect(["original  "]),"original  ")

    def test_draft_keeps_entities_and_declines_swapped_zones(self):
        def unexpected_model():
            raise AssertionError("An exact cost needs no inference")
        self.assertEqual(draft_line(unexpected_model,"rule","Put one character from your hand into your waiting room.",""),
                         "자신의 패에서 캐릭터 1장을 대기실에 놓는다.")
        bad=Mock()
        bad.translate.return_value="68142001에서 68142000로 3장을 이동"
        self.assertIsNone(draft_line(lambda:bad,"rule","Move 3 from your hand to your deck.",""))
        bad.translate.return_value="68142000에서 68142001로 2장을 이동"
        self.assertIsNone(draft_line(lambda:bad,"rule","Move 3 from your hand to your deck.",""))
        self.assertNotEqual(memory_revision("rule","Draw a card.",""),VERSION)
        self.assertEqual(memory_revision("name","Anticipation","XY"),VERSION)
        # A rejected result can fall back to a fully parsed and labeled source-order gloss.
        bad.translate.return_value="엉뚱한 내용으로 손실"
        gloss=draft_line(lambda:bad,"rule","Choose 2 《Unknown Trait》 characters in your waiting room.","")
        self.assertIn("영문 어순 풀이",gloss)
        for part in ("2","《Unknown Trait》","캐릭터","대기실"):
            self.assertIn(part,gloss)
        self.assertIsNone(draft_line(lambda:bad,"rule","Choose 2 quuxonite in your waiting room.",""))
        model=Mock()
        model.translate.return_value="비밀 모험 85127000"
        self.assertIn("나카노 이치카",draft_line(lambda:model,"name","Secret Adventure, Ichika Nakano","5HY"))
        model.translate.return_value="다른 사람의 모험"
        self.assertIsNone(draft_line(lambda:model,"name","Secret Adventure, Ichika Nakano","5HY"))
        self.assertNotEqual(memory_key("name","Rem","RZ"),memory_key("name","Rem","OTHER"))
        self.assertEqual(memory_key("rule","Draw a card.","RZ"),memory_key("rule","Draw a card.","OTHER"))
        card=dict(number="5HY/W101-E001",name="Unparalleled Beauty, Ichika Nakano",effect=None,need_name=True,need_effect=True)
        self.assertEqual(translated_fields(card),( "비할 데 없는 아름다움, 나카노 이치카",None,"GLOSSARY_TRANSLATED",None))
        card.update(legacy_key="catalog:WEISS:en:5HY/W101-E001",source_url="https://en.ws-tcg.com/cardlist/cardsearch/exec?cardno=5HY%2FW101-E001")
        self.assertTrue(eligible(card))
        self.assertFalse(eligible(card|{"source_url":"https://example.org"}))

    def test_memory_digest_is_checked_before_database_access(self):
        with TemporaryDirectory() as tmp:
            path=Path(tmp)/"memo.gz"
            with gzip.open(path,"wt") as out:
                out.write(json.dumps({"version":"incorrect"})+"\n")
            db=Mock()
            with self.assertRaisesRegex(ValueError,"SHA-256"):
                import_memory(db,path,"0"*64)
            db.transaction.assert_not_called()
            with self.assertRaisesRegex(ValueError,"Incompatible"):
                from contextlib import nullcontext
                db.transaction.return_value=nullcontext()
                import_memory(db,path,hashlib.sha256(path.read_bytes()).hexdigest())

    def test_confirmed_suffix_preserves_names_and_reuses_whole_name_readings(self):
        original="Rooftop Discussion, Ichika Nakano & Nino Nakano"
        card=dict(number="5HY/W61-E001",name=original,effect=None,need_name=True,need_effect=False)
        lookup=lambda kind,text,family: {"Rooftop Discussion":"옥상에서 나눈 이야기"}.get(text)
        self.assertEqual(translated_fields(card,lookup)[:3],("옥상에서 나눈 이야기, 나카노 이치카 · 나카노 니노",None,"MACHINE_TRANSLATION"))
        self.assertEqual(translated_fields(card,lambda *_:"이전 전체 메모")[0],"이전 전체 메모")
        self.assertIsNone(translated_fields({**card,"name":"Rooftop Discussion, Unknown & Nino Nakano"},lookup)[0])

    def test_pc_batch_validates_the_output_and_reuses_completed_units(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        model=Mock()
        model.tokenizer.encode.side_effect=lambda text,**_:text.split()
        model.tokenizer.decode.side_effect=lambda tokens:" ".join(tokens)
        model.model.translate_batch.side_effect=lambda inputs,**_:[
            SimpleNamespace(hypotheses=[["__ko__","새로운","비"]] if "Rain" in source else [["__ko__","숫자 오류"]])
            for source in inputs]
        cards=[{"code":"QA/W61-E001","name":"New Rain","expansion":"Test","ability":["-"]},
               {"code":"QA/W61-E002","name":"Number 5","expansion":"Test","ability":["-"]}]
        with sqlite3.connect(":memory:") as db, patch("tcg_worker.weiss_memory.sets",return_value=[("set",cards)]):
            db.execute("CREATE TABLE readings (revision,kind,family,original,translated,PRIMARY KEY(revision,kind,family,original))")
            self.assertEqual(prepare_gpu(db,None,lambda:model,None),2)
            self.assertEqual(dict(db.execute("SELECT original,translated FROM readings")),{"New Rain":"새로운 비","Number 5":None})
            self.assertEqual(prepare_gpu(db,None,lambda:model,None),0)
            model.model.translate_batch.assert_called_once()
