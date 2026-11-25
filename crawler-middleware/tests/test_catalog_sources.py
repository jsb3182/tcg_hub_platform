import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from tcg_worker.catalog_sources.bulk import pokemon_record, riftbound, weiss, yugioh
from tcg_worker.catalog_sources.card_names import PokemonNames, printed_name
from tcg_worker.catalog_sources.nivel import parse_detail
from tcg_worker.catalog_sources.transport import CatalogHTTP


class CatalogTests(unittest.TestCase):
    def test_localized_printings_prefer_exact_names_and_omit_ambiguous_matches(self):
        names = PokemonNames()
        for lang, name, printing in (("ko", "시험 카드", "asia:1"), ("ja", "テスト", "asia:1"),
                                     ("en", "Test", "en:1"), ("ja", "別名", "asia:2")):
            names.add(lang, {"name": name, "card_key": "shared", "print_key": printing})
        self.assertEqual(names.localized("시험 카드", "asia:1", "shared"),
                         {"ko": "시험 카드", "ja": "テスト", "en": "Test"})
        self.assertNotIn("ja", names.localized("시험 카드", None, "shared"))
        self.assertEqual(names.localized("다른 카드", "asia:1", "shared"), {"ko": "다른 카드"})
        self.assertEqual(printed_name("<ruby>名称<rt>めいしょう</rt></ruby> &amp; A"), "名称 & A")

    def test_korean_printing_without_short_set_code(self):
        row = pokemon_record({"ko_id": "example", "name": "테스트", "set_full_name": "테스트 제품",
                              "attacks": [{"name": "기술", "damage": 20, "effect": "효과"}]}, "R.json")
        self.assertEqual(row["external_id"], "ko:example")
        self.assertIsNone(row["pack_code"])
        self.assertEqual((row["pack_name"], row["effect"]), ("테스트 제품", "기술 20 효과"))

    def test_nivel_html_preserves_inline_icon_and_original_title(self):
        html = """<h2 id='subject'>가상 카드</h3><h2 id='type'>EX-01 / 유닛 / 파도</h3>
        <td class='h3'>레어도</td><td>R</td><td class='h3'>제품명</td><td>테스트 <예시></td>
        <div id='content'><img alt='패시브' src='/icon'> 테스트<br>다음 줄</div>"""
        card = parse_detail(html, "7")
        self.assertEqual((card["name"], card["number"], card["rarity"]), ("가상 카드", "EX-01", "R"))
        self.assertEqual(card["effect"], "[패시브] 테스트\n다음 줄")
        self.assertEqual(card["pack_name"], "테스트 <예시>")

    def test_rifthunt_link_uses_printing_uuid(self):
        fake = {"sets": [{"id": "X", "name": "Fixture", "released": "2026-01-01"}],
                "cards": [{"set": "X", "name": "Fixture Card", "printing_id": "printing-uuid", "id": "x-001"}]}
        with patch("tcg_worker.catalog_sources.bulk.document", return_value=fake):
            card = next(riftbound(Mock()))
        self.assertEqual(card["number"], "x-001")
        self.assertTrue(card["source_url"].endswith("/printing-uuid"))

    def test_weiss_uses_set_archives_and_deduplicates_printing_code(self):
        fixture = {"name": "Example", "code": "EX/W99-E001", "expansion": "Example Pack", "ability": ["One", "Two"]}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "set.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("repository/DB/EX_W99.json", json.dumps([fixture, fixture]))
            http = Mock()
            http.get.return_value = path
            with patch("tcg_worker.catalog_sources.bulk.revision", return_value="a" * 40):
                rows = list(weiss(http))
            self.assertEqual(len(rows), 1)
            self.assertEqual((rows[0]["pack_code"], rows[0]["effect"]), ("EX/W99", "One\nTwo"))

    def test_yugioh_keeps_reprints_and_skips_duplicate_rows(self):
        printings = [{"set_name": "Fixture", "set_code": "EX-001", "set_rarity": r} for r in ["C", "R", "C"]]
        card = {"id": 9, "name": "Fixture", "card_sets": printings, "ygoprodeck_url": "https://example.org/card/9"}
        pages = [[{"database_version": "v1"}], [{"set_name": "Fixture", "set_code": "EX"}],
                 {"meta": {"total_rows": 1}, "data": [card]}]
        with patch("tcg_worker.catalog_sources.bulk.document", side_effect=pages), \
             patch("tcg_worker.catalog_sources.bulk.ygo_names", return_value={}):
            rows = list(yugioh(Mock()))
        self.assertEqual([r["rarity"] for r in rows], ["C", "R"])
        self.assertNotEqual(rows[0]["external_id"], rows[1]["external_id"])

    def test_cache_replaces_completed_version_and_forwards_rate_limit(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"CATALOG_CACHE_ROOT": tmp}):
            http = CatalogHTTP()
            first, second = Path(tmp) / ("a" * 64), Path(tmp) / ("b" * 64)
            first.write_bytes(b"old")
            second.write_bytes(b"new")
            with http.scan("WEISS"):
                http.remember_revision("fixture", first)
                http.remember_revision("fixture", second)
                self.assertFalse(first.exists())
                self.assertTrue(second.exists())
                error = HTTPError("https://example.org/data", 429, "retry", {"Retry-After": "120"}, None)
                with patch.object(http.opener, "open", side_effect=error), self.assertRaises(HTTPError) as caught:
                    http.get("https://example.org/data")
                self.assertEqual(caught.exception.headers["Retry-After"], "120")
            index = json.loads((Path(tmp) / ".WEISS.revisions.json").read_text())
            self.assertEqual(list(index.values()), [[second.name]])
