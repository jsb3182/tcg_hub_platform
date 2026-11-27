import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock

from tcg_worker.catalog_sources import pokemon_weiss_releases as releases
from tcg_worker.feeds import FetchError


def pokemon_row(slug, name, day="February 6, 2027"):
    return f'<tr><td><a href="{slug}" class="prod-name">Pokémon TCG: {name}</a></td><td class="td-date">{day}</td></tr>'


class ProductCalendarTests(unittest.TestCase):
    def test_unknown_new_series_and_independently_confirmed_standalone_sets(self):
        first = pokemon_row("/en/products/Future", "Next Generation—First Light")
        rows = [first, first, pokemon_row("/en/products/test", "Unnamed Era"),
                pokemon_row("/en/products/physical", "Next Generation Battle Deck"),
                pokemon_row("/en/products/ambiguous", "Discovery"),
                pokemon_row("/en/products/other", "Wrong Date"),
                pokemon_row("/en/products/live", "Next Generation—Digital Tournament"),
                pokemon_row("/en/products/quarter", "Next Generation—Later", "Q2 2027"),
                pokemon_row("https://elsewhere.invalid/en/products/wrong", "Next Generation—Untrusted")]
        result = releases.pokemon_schedule("<table>"+"".join(rows)+"</table>",
                                           {("unnamed era", "2027-02-06"), ("wrong date", "2027-02-05")})
        self.assertEqual({"na-future", "na-test", "na-physical"}, {r["key"] for r in result})
        self.assertTrue(all(r["region"] == "NA" and r["date"] == "2027-02-06" for r in result))

    def test_japan_nested_mobile_title_duplicates_and_event_exclusion(self):
        stamp = '<p class="products__salesdate">発売日：2027年3月26日(金)</p>'
        category = '<li class="products__catItem">ブースターパック</li>'
        base = '<a class="products__link" href="/products/pack/">'
        one = base + category + '<p class="products__name">楽園追放' + stamp + '</p></a>'
        two = base + category + '<p class="products__name">楽園追放</p>' + stamp + '</a>'
        other = two.replace('ブースターパック','サプライ').replace('/pack/', '/sleeve/')
        row, = releases.weiss_schedule(one + two + other, "JP")
        self.assertEqual(("jp-pack","ブースターパック 楽園追放","2027-03-26"), (row["key"],row["name"],row["date"]))
        with self.assertRaisesRegex(ValueError, "inconsistent"):
            releases.weiss_schedule(one + two.replace("26日", "25日"), "JP")

    def test_robots_policy_prevents_page_request_and_honors_crawl_delay(self):
        with TemporaryDirectory() as tmp:
            robots = Path(tmp) / "robots"
            robots.write_text("User-agent: *\nDisallow: /en/Items/", encoding="utf-8")
            http = Mock()
            http.get.return_value = robots
            with self.assertRaises(FetchError):
                releases._page(http, releases.POKEMON_NA)
            self.assertEqual(1, http.get.call_count)
            robots.write_text("User-agent: *\nCrawl-delay: 5\nAllow: /", encoding="utf-8")
            replies = Path(tmp) / "page"
            replies.write_bytes(b"<table></table>")
            http.get.side_effect = [robots, replies]
            self.assertEqual(b"<table></table>",releases._page(http,releases.POKEMON_NA))
            self.assertEqual(5,http.get.call_args.kwargs["delay"])

    def test_seed_keeps_official_dates_regions_and_assortments_separate(self):
        seed = Path(releases.__file__).with_name("release_data") / "pokemon_weiss.json"
        rows = json.loads(seed.read_bytes())
        keys = {(r["game"],r["key"]): r for r in rows}
        self.assertEqual(len(rows), len(keys))
        korean_pokemon = keys["POKEMON", "kr-938"]
        self.assertEqual(("2026-08-21", "M6", "KR"),
                         (korean_pokemon["date"], korean_pokemon["catalogCode"], korean_pokemon["region"]))
        self.assertNotIn("catalogCode", keys["POKEMON", "kr-991"])
        self.assertEqual("2026-09-19", keys["WEISS", "kr-bp-nik2"]["date"])
        self.assertEqual("2026-09-25", keys["WEISS", "en-bp-nik2"]["date"])
        self.assertNotIn("catalogCode", keys["WEISS", "kr-bp-nik2"])
        self.assertEqual("2026-12-23", keys["WEISS", "en-bp-p30"]["date"])
        self.assertEqual("2027-02-06", keys["POKEMON", "na-pokemon-tcg-mega-evolutionflowing-fists"]["date"])
