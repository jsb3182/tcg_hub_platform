from unittest import TestCase

from tcg_worker.catalog_sources.weiss_character_names import character_references


class CharacterReferenceTests(TestCase):
    def test_article_identity_depends_on_the_series(self):
        date_a_live = character_references("Kotori & Kotori", "DAL")
        love_live = character_references("Kotori", "LL")
        self.assertEqual([ref["title"] for ref in date_a_live], ["이츠카 코토리"])
        self.assertEqual([ref["title"] for ref in love_live], ["미나미 코토리"])
        self.assertEqual(character_references("Kotori", "UNKNOWN"), [])
        self.assertEqual(character_references("Kotorin", "LL"), [])

    def test_series_name_in_a_spell_title_is_not_character_evidence(self):
        self.assertEqual(character_references("Cardcaptor Sakura: GALE", "CCS"), [])
        self.assertEqual(character_references("Sakura & Tomoyo", "CCS")[0]["korean"], "사쿠라")
