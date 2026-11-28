from unittest import TestCase

from tcg_worker.catalog_sources.weiss_korean import complete_effect


class AbilityTemplateTests(TestCase):
    def test_another_character_is_the_trigger_but_this_card_receives_the_bonus(self):
        effect = "【AUTO】 When another of your characters becomes 【REVERSE】 in battle, this card gets +1000 power until end of turn."
        self.assertEqual(complete_effect(effect), "【자동】자신의 다른 캐릭터가 배틀 중 리버스 상태가 되었을 때, 턴 종료 시까지 이 카드는 파워 +1000을 얻는다.")

    def test_trait_union_is_not_a_conjunction(self):
        line = "【CONT】 If you have 3 or more other 《Magic》 or 《Weapon》 characters, this card gets +1500 power."
        self.assertEqual(complete_effect(line), "【지속】자신의 다른 《마법》 또는 《무기》 캐릭터가 3장 이상이라면 이 카드는 파워 +1500을 얻는다.")
        self.assertIsNone(complete_effect(line.replace("》 or 《", "》 and 《")))
        self.assertIsNone(complete_effect(line.replace("Magic", "Unrecorded")))
        self.assertIsNone(complete_effect(line + " You may then draw a card."))

    def test_optional_draw_and_mandatory_disposal_stay_distinct(self):
        line = ("【AUTO】 When this card is placed on the stage from your hand, look at up to 4 cards from the top of your deck, "
                "choose up to 1 card from among them, put it into your hand, and put the rest into your waiting room.")
        self.assertEqual(complete_effect(line), "【자동】이 카드가 패에서 무대에 놓였을 때, 자신의 덱 위에서 카드를 최대 4장 본다. 그중 최대 1장을 골라 패에 넣고 나머지는 대기실에 놓는다.")
        self.assertIsNone(complete_effect(line.replace("your waiting room", "your stock")))
