import tempfile
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

from tcg_worker.catalog_sources.onepiece import CARD_LIST, Index, korean


class KoreanHistory(unittest.TestCase):
    def read(self, failure):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        class Source:
            root = Path(directory.name)

            def get(self, url, **options):
                parsed = urlsplit(url)
                if parsed.path == "/robots.txt":
                    body = "User-agent: *\nAllow: /\n"
                elif url == CARD_LIST:
                    body = '<select><option value="[OPK-01] A">A</option><option value="[OPK-02] B">B</option></select>'
                elif parse_qs(parsed.query)["series"] == ["[OPK-01] A"]:
                    raise failure
                else:
                    body = '<div class="card_sch_list"><button class="item"><p class="cardNumber">OP02-001</p><p class="cardName">시험 인쇄본</p></button></div>'
                path = self.root / "response"
                path.write_text(body,encoding="utf-8")
                return path
        index = Index()
        korean(index,Source())
        return index

    def test_a_timeout_on_one_product_preserves_the_other_products_turn(self):
        index = self.read(TimeoutError())
        self.assertTrue(index.korean_incomplete)
        self.assertEqual(index.editions["OP02-001"]["ko"][1]["name"],"시험 인쇄본")

    def test_respects_provider_wide_retry_after(self):
        with self.assertRaises(HTTPError) as result:
            self.read(HTTPError(CARD_LIST,429,"Retry later",{"Retry-After":"3600"},None))
        self.assertEqual(result.exception.headers["Retry-After"],"3600")
