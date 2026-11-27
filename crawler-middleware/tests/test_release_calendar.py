import json
import unittest

from tcg_worker.release_calendar import DATA, GAMES, checked


class BundledReleases(unittest.TestCase):
    def test_offline_announcements_have_regions_and_verifiable_product_days(self):
        rows = checked(row for file in DATA.glob("*.json") for row in json.loads(file.read_text("utf-8")))
        # The five North American Yu-Gi-Oh! announcements are seeded by Flyway.
        self.assertEqual({r["game"] for r in rows}, GAMES - {"YUGIOH"})
        self.assertTrue(all(r["url"] and r["region"] for r in rows))
        self.assertTrue(any(r["game"]=="POKEMON" and r["region"]=="KR" and r.get("catalogCode") for r in rows))
        self.assertTrue(any(r["game"]=="WEISS" and r["region"]=="JP" for r in rows))
        self.assertTrue(any(r["game"]=="RIFTBOUND" and r["region"]=="KR" and r["date"]=="2026-12-11" for r in rows))
        self.assertTrue(any(r["game"]=="NIVEL" and r.get("code")=="SB03" and r["date"]=="2026-12-18" for r in rows))
        self.assertTrue(any(r["game"]=="ONEPIECE" and r.get("code")=="OP-19" and r["date"]=="2027-03-05" for r in rows))
