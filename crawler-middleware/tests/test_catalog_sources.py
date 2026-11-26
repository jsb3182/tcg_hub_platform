import io
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
        <td class='h3'>레어도</td><td>R</td><tr><td class='h3' colspan='3'>효과</td></tr>
        <tr><td colspan='4'>여러 줄 효과</td></tr>
        <tr><td class='h3'>제품명</td><td>테스트 <예시></td></tr>
        <div id='content'><img alt='패시브' src='/icon'> 테스트<br>다음 줄</div>"""
        card = parse_detail(html, "7")
        self.assertEqual((card["name"], card["number"], card["rarity"]), ("가상 카드", "EX-01", "R"))
        self.assertEqual(card["effect"], "[패시브] 테스트\n다음 줄")
        self.assertEqual(card["pack_name"], "테스트 <예시>")
        self.assertFalse(any("\n" in key for key in card["specs"]))

    def test_rifthunt_numbers_do_not_identify_printings(self):
        fields = [
            {"riftboundId":"x-001","num":1,"id":"legacy-import-1"},
            {"riftboundId":"x-001","num":1},
            {"num":0,"id":"legacy-token"},
            {"id":"legacy-only"},
            {},
        ]
        rows = [{"set":"X","name":"Fixture Card","printing_id":f"printing-{i}",**data}
                for i,data in enumerate(fields)]
        snapshot = {"sets":[{"id":"X","name":"Fixture"}],"cards":rows}
        with patch("tcg_worker.catalog_sources.bulk.document", return_value=snapshot):
            cards = list(riftbound(Mock()))
        self.assertEqual([c["number"] for c in cards], ["x-001","x-001","0","legacy-only",None])
        for i,card in enumerate(cards):
            self.assertEqual(card["external_id"], f"en:printing-{i}")
            self.assertEqual(card["source_url"], f"https://api.rifthunt.com/cards/printing-{i}")

    def test_rifthunt_bulk_cache_survives_manual_refresh_for_24_hours(self):
        snapshot = {"sets":[{"id":"X","name":"Fixture"}],
                    "cards":[{"set":"X","name":"Fixture Card","printing_id":"fixture","riftboundId":"x-001"}]}
        def response():
            stream = io.BytesIO(json.dumps(snapshot).encode())
            stream.headers = {}
            return stream

        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"CATALOG_CACHE_ROOT":tmp}):
            http = CatalogHTTP()
            with patch.object(http.opener, "open", side_effect=[response(),response()]) as network:
                self.assertEqual(len(list(riftbound(http))), 1)
                cached = next(Path(tmp).iterdir()).stat().st_mtime
                restarted = CatalogHTTP()
                with patch("tcg_worker.catalog_sources.transport.time.time", return_value=cached+86399), \
                     patch.object(restarted.opener, "open", side_effect=AssertionError("early network fetch")):
                    self.assertEqual(list(riftbound(restarted))[0]["number"], "x-001")
                self.assertEqual(network.call_count, 1)
                with patch("tcg_worker.catalog_sources.transport.time.time", return_value=cached+86401):
                    self.assertEqual(len(list(riftbound(http))), 1)
                self.assertEqual(network.call_count, 2)

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
        pages = [[{"database_version": "v1"}], [{"set_name": "Fixture", "set_code": "EX", "tcg_date": "2020-01-02"}],
                 {"meta": {"total_rows": 1}, "data": [card]}]
        with patch("tcg_worker.catalog_sources.bulk.document", side_effect=pages), \
             patch("tcg_worker.catalog_sources.bulk.ygo_names", return_value={}):
            rows = list(yugioh(Mock()))
        self.assertEqual([r["rarity"] for r in rows], ["C", "R"])
        self.assertEqual([r["pack_tcg_date"] for r in rows], ["2020-01-02"] * 2)
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
