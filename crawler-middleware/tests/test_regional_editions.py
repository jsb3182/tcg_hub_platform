import unittest

from tcg_worker.catalog_sources.onepiece import Index, edition, korean_facts, korean_page, preserve_partial_korean
from tcg_worker.catalog_sources.card_names import PokemonNames, pokemon_edition, pokemon_effect

class EditionTests(unittest.TestCase):
    def test_onepiece_korean_facts_follow_the_selected_printed_edition(self):
        index = Index()
        number = "EB01-003"
        original = "https://en.onepiece-cardgame.com/cardlist/"
        official = "https://www.onepiece-cardgame.kr/cardlist.do?series=OPK-14"
        index.add(number, "en", edition("Card", "Effect", None, original), 0, "EB-01", "Original", power=6000)
        page = """<div class=card_sch_list><button class=item>
            <p class=cardNumber>EB01-003_P2<p class=cardName>시험 카드<p class=cardGet>[OPK-14] 부스터
            <p class=cardType>캐릭터<p class=cardAttr>참격<p class=cardPoint>신세계/시험 해적단
            <p class=life>3<p class=power>5000<p class=cardCounter>0</button></div>"""
        korean_page(index, page, official, "")
        rows = list(index.records())
        self.assertEqual(len(rows), 2)
        for row in rows:
            self.assertEqual(row["specs"]["regionalFacts"], {"ko": {
                "sourceUrl": official, "productCode": "OP-14", "attribute": "참격",
                "traits": ["신세계", "시험 해적단"], "cost": 3, "power": 5000, "counter": 0
            }})
            self.assertEqual(row["specs"]["power"], 6000)
        leader = korean_facts({"cardType": "리더", "life": "4", "cardPoint": "-", "cardCounter": "-"}, "PROMO", official)
        self.assertEqual(leader, {"life": 4, "sourceUrl": official})
        self.assertEqual(korean_facts({"cardType": "불명", "life": "3", "power": "?"}, None, official), {})

    def test_partial_korean_enrichment_preserves_old_edition_identity(self):
        official = "https://www.onepiece-cardgame.kr/cardlist.do?page=1"
        old = {"names": {"ko": "시험"}, "sources": {"ko": official}, "productCode": "EB-01",
               "nameBasis": {"ko": "PRINTED_NAME"}, "regionalFacts": {
                   "ko": {"sourceUrl": official, "productCode": "EB-01", "life": 4}}}
        key = "catalog:ONEPIECE:EB-01:EB01-003"
        number = "EB01-003"
        card = {"number": number, "korean_incomplete": True, "specs": {"productCode": "EB-01", "names": {"en": "Test"}}}

        class Previous:
            def execute(self, query, params):
                return self

            def fetchall(self):
                return [(key, number, old)]

        preserve_partial_korean(Previous(), {key: card})
        self.assertEqual(card["specs"]["regionalFacts"], old["regionalFacts"])
        self.assertEqual(card["specs"]["names"], {"en": "Test", "ko": "시험"})

    def test_official_onepiece_fields_use_direct_text_and_ignore_unrelated_image_urls(self):
        body="""<div class="card_sch_list"><button class="item">
        <p class="cardNumber">OP01-001<p class="cardName">시험 리더<p class="cardText">효과
        <p class="cardGet">[OPK-01] 시험<p class="cardType">리더<p class="cardColor">적색
        <img class="image" src="https://example.invalid/card.jpg"></button></div>
        <a class="pagi_next" href="?page=1">다음</a>"""
        index=Index()
        self.assertEqual(korean_page(index,body,"https://www.onepiece-cardgame.kr/cardlist.do",""),1)
        card,=index.records()
        self.assertEqual((card["external_id"],card["name"],card["effect"]),("OP-01:OP01-001","시험 리더","효과"))
        self.assertEqual(card["specs"]["colors"],["red"])
        self.assertEqual(card["specs"]["images"],{})
        self.assertEqual(card["specs"]["imageProducts"], {})
        self.assertEqual(card["specs"]["imageSources"], {})

    def test_onepiece_reprint_keeps_the_adopted_images_product_and_source(self):
        number = "EB01-003"
        korean = "https://www.onepiece-cardgame.kr/cardlist.do?series=OPK-14"
        original = "https://en.onepiece-cardgame.com/cardlist/?series=eb01"
        reprint = "https://en.onepiece-cardgame.com/cardlist/?series=op14"
        index = Index()
        page = """<div class="card_sch_list"><button class="item">
            <p class="cardNumber">EB01-003_P2</p><p class="cardName">카드</p>
            <p class="cardGet">[OPK-14] 부스터 팩 창해의 칠걸</p>
            <p class="cardText">효과</p><img class="image" src="/fileDownload?downname=parallel">
            </button></div>"""
        korean_page(index, page, korean, "")
        index.add(number, "en", edition("Card", "Effect", "original-art", original), 0, "EB-01", "Original")
        index.add(number, "en", edition("Card", "Effect", "reprint-art", reprint), 2, "OP-14", "Reprint")
        rows = {row["external_id"]: row["specs"] for row in index.records()}
        self.assertEqual(set(rows), {"EB-01:EB01-003", "OP-14:EB01-003"})
        for key, en_source, en_image in (("EB-01", original, "original-art"), ("OP-14", reprint, "reprint-art")):
            specs = rows[f"{key}:{number}"]
            self.assertEqual(specs["productCode"], key)
            self.assertEqual(specs["imageProducts"], {"en": key, "ko": "OP-14"})
            self.assertEqual(specs["imageSources"], {"en": en_source, "ko": korean})
            self.assertEqual(specs["images"]["en"], en_image)
            self.assertTrue(specs["images"]["ko"].endswith("downname=parallel"))
            self.assertEqual(specs["texts"], {"en": "Effect", "ko": "효과"})
            self.assertEqual(specs["names"], {"en": "Card", "ko": "카드"})

    def test_onepiece_unknown_image_product_is_not_inferred_from_collector_number(self):
        number = "OP01-001"
        index = Index()
        index.add(number, "en", edition("Card", None, None, "set-list"), 0, "OP-01", "Set")
        index.add(number, "ko", edition("카드", "효과", "promo-art", "promo-list"), 0, "PROMO", "프로모션")
        index.add(number, "ja", edition("カード", None, "other-art", "archive"), 0)
        for row in index.records():
            self.assertEqual(row["specs"]["images"], {"ko": "promo-art", "ja": "other-art"})
            self.assertEqual(row["specs"]["imageProducts"], {})
            self.assertEqual(row["specs"]["imageSources"], {"ko": "promo-list", "ja": "archive"})

    def test_pokemon_matches_effect_and_picture_independently_by_confirmed_identity(self):
        evidence=PokemonNames()
        group={"card_key":"face"}
        art={("bw1","1","Card"):"https://assets.tcgdex.net/en/bw/bw1/1/high.webp"}
        for lang,card in [
            ("ko",dict(name="카드",print_key="asia:1",effect="효과")),
            ("en",dict(name="Card",print_key="en:1",set_code="BW1",number="001",effect="Effect")),
            ("ja",dict(name="カード",print_key="asia:1",effect="効果")),
            ("ja",dict(name="カード",print_key="asia:2",effect="別の効果"))]:
            card.update(group)
            evidence.add(lang,card,pokemon_edition(lang,card,art))
        result=evidence.editions("카드","asia:1","face")
        self.assertEqual(result["texts"],{"ko":"효과","ja":"効果","en":"Effect"})
        self.assertEqual(result["images"],{"en":next(iter(art.values()))})
        self.assertNotIn("ja",evidence.editions("카드",None,"face")["texts"])
        self.assertEqual(pokemon_effect({"attacks":[{"name":"技","damage":{"amount":20,"suffix":"+"}}]}),"技 20+")
