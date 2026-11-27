from unittest import TestCase
from unittest.mock import Mock

from tcg_worker.card_readings import korean_field


class KoreanReadingTests(TestCase):
    def test_retains_lines_and_checks_rule_numbers(self):
        model=Mock()
        model.translate.side_effect=["카드 2장을 뽑는다.", "이 카드는 파워가 +1000 상승한다."]
        value=korean_field(model,"Draw 2 cards.\nThis card gets +1000 power.","en",8000)
        self.assertEqual(value,"카드 2장을 뽑는다.\n이 카드는 파워가 +1000 상승한다.")
        for bad in ("카드 3장을 뽑는다.", "Draw 2 cards.", "カード2장을 뽑는다."):
            with self.subTest(bad=bad):
                self.assertIsNone(korean_field(Mock(translate=Mock(return_value=bad)),"Draw 2 cards.","en",8000))
