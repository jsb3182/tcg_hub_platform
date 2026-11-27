import json
import unittest
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock

from tcg_worker.wiki_cards import checked, import_wiki_cards


def fixture():
    return {"game": "YUGIOH", "title": "표본", "url": "https://namu.wiki/w/%ED%91%9C%EB%B3%B8",
            "snapshotDate": "2021-03-01", "snapshotUrl": "https://example.org/2021",
            "verificationUrl": "https://www.db.yugioh-card.com/yugiohdb/card_search.action?ope=2&cid=234",
            "match": {"cid": 234, "passcode": "00000300"}, "names": {"ko": "표본"}, "facts":{"atk": 0}}


class WikiCardTests(unittest.TestCase):
    def test_stable_card_identifiers_and_independent_printing_evidence(self):
        ygo = checked({**fixture(), "printingNumber": "TST-KR000"})
        self.assertEqual((ygo["lookup_key"], ygo["passcode"], ygo["printing_number"]), ("cid:234", "300", None))
        self.assertEqual(ygo["facts"], {"atk": 0, "printingNumber": "TST-KR000"})
        other = checked({**fixture(), "game": "WEISS", "match": {"catalogKey":"catalog:WEISS:en:QA-001","number":"QA-001"},
                         "verificationUrl": "https://en.ws-tcg.com/cardlist/cardsearch/exec"})
        self.assertEqual(other["printing_number"], "QA-001")

    def test_mismatched_documents_and_unstructured_values_are_rejected(self):
        for edit in [{"url":"https://namu.wiki/w/other"}, {"url":"https://namu.wiki.example/w/표본"},
                     {"verificationUrl":"https://www.db.yugioh-card.com/?cid=235"}, {"match":{"cid":""}},
                     {"facts":{"effect":"full article"}}, {"facts":{"level":True}}, {"names":{"jp":"名前"}}]:
            with self.subTest(edit=edit), self.assertRaises((ValueError, KeyError)):
                checked({**fixture(), **edit})
        with TemporaryDirectory() as tmp:
            file=Path(tmp)/"wiki.json"
            file.write_text(json.dumps([fixture(),deepcopy(fixture())]))
            db=MagicMock()
            with self.assertRaises(ValueError):
                import_wiki_cards(db,file)
            db.execute.assert_not_called()
