import gzip
import hashlib
import importlib.util
import io
import json
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
from build_namuwiki_yugioh import articles, build, identities
from verify_namuwiki_yugioh import confirm, publisher


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.api = {"id": 123, "name": "Example", "misc_info": [{"konami_id": 999}], "type": "Xyz Monster",
                    "level": 3, "atk": 1000, "def": 2000, "attribute": "LIGHT", "race": "Dragon"}
        self.page = self.root / "page.json"
        self.page.write_text(json.dumps({"data": [self.api]}), "utf8")
        self.yaml = self.root / "source.tar.gz"
        with tarfile.open(self.yaml, "w:gz") as bundle:
            for cid, ko in [(999, "예시"), (998, "다른 예시")]:
                body = json.dumps({"konami_id": cid, "name": {"en": "Example", "ko": ko, "ja": "例"},
                                   "sets": {"ko": [{"set_number": "ST-K100"}]}}).encode()
                entry = tarfile.TarInfo("project/data/cards/" + str(cid) + ".json")
                entry.size = len(body)
                bundle.addfile(entry, io.BytesIO(body))
        self.article = {"title": "예시", "text": "한글판 명칭 예시\n일어판 명칭 例\n영어판 명칭 Example\n"
                        "랭크 속성 종족 공격력 수비력\n3 빛 드래곤족 1000 2000\nST-K100\n해설용 문장"}
        self.official = ("예시", {"rank": 3, "atk": 1000, "def": 2000, "race": "드래곤족", "attribute": "빛"},
                         {"ST-K100"})
        self.index = identities(self.yaml, [self.page])
        self.origin = "https://example.org/version/2021-03-01"

    def outputs(self, records, official=None):
        getter = lambda link: self.official if official is None else official
        return list(build(self.index, lambda: iter(records), "2021-03-01", self.origin, getter))

    def test_gzip_and_multiple_shards_preserve_row_and_facts_only(self):
        ignored, used = self.root / "part1.jsonl", self.root / "part2.jsonl.gz"
        ignored.write_text(json.dumps({"title": "다른 문서", "text": "일반 문서"}), "utf8")
        with gzip.open(used, "wt", encoding="utf8") as f:
            f.write(json.dumps(self.article))
        result = list(build(self.index, lambda: articles([ignored, used]), "2021-03-01", self.origin,
                            lambda url: self.official))
        self.assertEqual(len(result), 1)
        row = result[0]
        self.assertEqual((row["match"], row["snapshotRow"], row["printingNumber"]),
                         ({"cid": 999, "passcode": "00000123"}, 1, "ST-K100"))
        self.assertEqual(row["articleSha256"], hashlib.sha256(self.article["text"].encode()).hexdigest())
        self.assertEqual(row["names"], {"ko": "예시", "en": "Example", "ja": "例"})
        self.assertNotIn("해설", json.dumps(row, ensure_ascii=False))

    def test_duplicate_or_conflicting_sources_do_not_match(self):
        self.assertEqual([], self.outputs([self.article, self.article]))
        self.assertEqual([], self.outputs([self.article], ("예시", {**self.official[1], "rank": 7}, {})))
        split = {**self.article, "text": self.article["text"].replace("랭크", "한글판 명칭 다른 예시\n랭크")}
        self.assertEqual([], self.outputs([split]))
        mutated = {**self.article, "text": self.article["text"].replace("명칭 例", "명칭 다른 일어판 이름")}
        self.assertNotIn("ja", self.outputs([mutated])[0]["names"])
        self.assertNotIn("printingNumber", self.outputs([self.article], (*self.official[:2], set()))[0])

    def test_digest_id_and_publisher_fields(self):
        row = self.outputs([self.article])[0]
        self.assertFalse(confirm({**row, "articleSha256": "f" * 64}, self.article, self.api,
                                 self.official, self.origin))
        self.assertFalse(confirm(row, self.article, {**self.api, "id": 234}, self.official, self.origin))
        html = "<title>예시 | 카드 상세 | 공식</title><div id='update_list'><b class='card_number'>ST-K100</b></div>"
        self.assertEqual(publisher(html), ("예시", {}, {"ST-K100"}))
