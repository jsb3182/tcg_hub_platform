import unittest

from tcg_worker.catalog_sources.onepiece import Index, korean_page
from tcg_worker.catalog_sources.card_names import PokemonNames, pokemon_edition, pokemon_effect

class EditionTests(unittest.TestCase):
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
