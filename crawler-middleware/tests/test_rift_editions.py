import json
import os
import tempfile
import unittest
from pathlib import Path
from urllib.error import HTTPError

from tcg_worker.catalog_sources.bulk import riftbound
from tcg_worker.catalog_sources.rift_editions import GALLERIES, ORIGIN


def asset(n):
    return f"https://cmsassets.rgpub.io/sanity/images/dsfx7636/game_data_live/{n:040x}-744x1039.png"


def printing(number, name, picture, code=None):
    return {"id": f"legacy-{picture}", "printing_id": f"fixture-{picture}", "riftboundId": f"ogn-{number:03}-298",
            "name": name, "cleanName": name, "set": code or "OGN", "num": number, "imgUrl": asset(picture),
            "text": "Original English rules."}


def official(card, name, picture, subtitle=None, rule=""):
    return {"id": card["riftboundId"], "name": name, "subtitle": subtitle, "collectorNumber": card["num"],
            "publicCode": f"OGN-{card['num']:03}/298",
            "cardImage": {"url": asset(picture) + "?accountingTag=RB", "accessibilityText": name + "."},
            "set": {"value": {"id": "OGN"}},
            "text": {"richText": {"type": "html", "body": rule}}}


class Fixture:
    def __init__(self, root, cards, en, ko):
        self.root = root
        self.calls = []
        (root / "catalog.json").write_text(json.dumps({"sets": [{"id": "OGN", "name": "Origins"}], "cards": cards}))
        (root / "robots").write_text("User-agent: *\nAllow: /\n", encoding="utf8")
        self.write("en-us", en)
        self.write("ko-kr", ko)

    def write(self, locale, cards):
        document = {"props": {"pageProps": {"page": {"locale": locale, "blades": [
            {"type": "riftboundCardGallery", "cards": {"items": cards}}]}}}}
        (self.root / locale).write_text('<html><script id="__NEXT_DATA__" type="application/json">'+
                                       json.dumps(document, ensure_ascii=False)+'</script></html>', encoding="utf8")

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        urls = {**{v: k for k, v in GALLERIES.items()},
                ORIGIN+"/robots.txt": "robots", "https://api.rifthunt.com/bulk/cards": "catalog.json"}
        return self.root / urls[url]


class RiftEditions(unittest.TestCase):
    def test_signature_slug_requires_matching_provider_ids_public_code_and_unique_art(self):
        signed = {**printing(303, "English fixture", 31), "id": "ogn-303-star-298",
                  "riftboundId": "ogn-303*-298", "variant": "signature"}
        regular = printing(303, "English regular", 30)
        en = {**official(signed, "English fixture", 31), "id": signed["id"], "publicCode": "OGN-303*/298"}
        ko = {**official(signed, "한글 서명판", 32, rule="<p>테스트 효과</p>"), "id": signed["id"], "publicCode": "OGN-303*/298"}
        with tempfile.TemporaryDirectory() as tmp:
            def load(cards, english, korean):
                return list(riftbound(Fixture(Path(tmp), cards, english, korean)))
            item, other = load([signed, regular], [en, official(regular, "Regular", 30)],
                               [ko, official(regular, "일반판", 33)])
            self.assertEqual((item["number"], item["external_id"]), ("ogn-303*-298", "en:fixture-31"))
            self.assertEqual(item["specs"]["editionEvidence"]["ko"]["publisherId"], "ogn-303-star-298")
            self.assertEqual(item["specs"]["texts"]["ko"], "테스트 효과")
            self.assertEqual(item["specs"]["images"]["ko"], asset(32) + "?accountingTag=RB")
            self.assertEqual(other["specs"]["images"]["ko"], asset(33) + "?accountingTag=RB")
            for wrong in ({"id": "ogn-304-star-298"}, {"variant": "overnumbered"}, {"num": 304},
                          {"riftboundId": "sfd-303*-298", "id": "sfd-303-star-298"}, {"imgUrl": asset(999)}):
                self.assertNotIn("names", load([{**signed, **wrong}], [en], [ko])[0]["specs"])
            for invalid_en, invalid_ko in (([en], [ko,ko]), ([en], [{**ko,"publicCode":"OGN-303/298"}]),
                    ([{**en,"publicCode":"OGN-303/298"}], [{**ko,"publicCode":"OGN-303/298"}])):
                self.assertNotIn("names", load([signed], invalid_en, invalid_ko)[0]["specs"])
            duplicate = {**signed, "riftboundId": signed["id"], "printing_id": "different-id"}
            self.assertTrue(all("names" not in r["specs"] for r in load([signed, duplicate], [en], [ko])))

    def test_exact_english_asset_binds_region_and_preserves_original_and_rule_symbols(self):
        champion = printing(1, "Fixture, Fiery", 10)
        spell = printing(2, "Fixture Spell", 20)
        english = [official(champion, "Fixture", 10, "Fiery"), official(spell, "Fixture Spell", 20, "Champion")]
        korean = [official(champion, "용사", 11, "화염", "<p>[가속] :rb_energy_1:<br>한 장을 뽑습니다.</p>"),
                  official(spell, "주문", 21, "용사")]
        with tempfile.TemporaryDirectory() as tmp:
            http = Fixture(Path(tmp), [champion,spell], english, korean)
            hero, magic = riftbound(http)
            self.assertEqual(hero["external_id"], "en:fixture-10")
            self.assertEqual(hero["name"], "Fixture, Fiery")
            self.assertEqual(hero["effect"], "Original English rules.")
            specs = hero["specs"]
            self.assertEqual(specs["language"], "en")
            self.assertEqual(specs["names"]["ko"], "용사, 화염")
            self.assertEqual(specs["texts"]["ko"], "[가속] :rb_energy_1:\n한 장을 뽑습니다.")
            self.assertEqual(specs["nameBasis"]["ko"], "PRINTED_NAME")
            self.assertEqual(specs["editionEvidence"]["ko"]["publicCode"], "OGN-001/298")
            self.assertEqual(specs["sources"]["ko"], GALLERIES["ko-kr"])
            self.assertEqual(specs["images"], {"en": asset(10) + "?accountingTag=RB", "ko": asset(11) + "?accountingTag=RB"})
            self.assertEqual(specs["imageSources"], {"ko": GALLERIES["ko-kr"], "en": GALLERIES["en-us"]})
            self.assertEqual(specs["productCode"], "OGN")
            self.assertEqual(specs["imageProducts"], {"ko": "OGN", "en": "OGN"})
            self.assertEqual(magic["specs"]["names"]["ko"], "주문")
            self.assertNotIn("texts",magic["specs"])
            self.assertEqual(len(http.calls), 4)
            self.assertTrue(all(kwargs["ttl"] >= 7*86400 for url,kwargs in http.calls if url in GALLERIES.values()))

    def test_identical_or_unverified_assets_keep_the_korean_name_and_only_the_verified_image(self):
        cards = [printing(i, f"English {i}", i) for i in range(1, 6)]
        en = [official(card, card["name"], i) for i, card in enumerate(cards, 1)]
        ko = [official(card, f"한글 {i}", i + 20) for i, card in enumerate(cards, 1)]
        ko[0]["cardImage"]["url"] = en[0]["cardImage"]["url"]
        ko[1]["cardImage"]["accessibilityText"] = "Missing localized caption"
        ko[2]["cardImage"]["url"] = ko[2]["cardImage"]["url"].replace("cmsassets.rgpub.io", "cdn.example")
        ko[3]["cardImage"]["url"] = asset(24) + "?unrecognized=1"
        ko[4]["cardImage"]["url"] = asset(25) + "#foreign"
        with tempfile.TemporaryDirectory() as tmp:
            for item in riftbound(Fixture(Path(tmp), cards, en, ko)):
                self.assertEqual(set(item["specs"]["images"]), {"en"})
                self.assertEqual(set(item["specs"]["imageSources"]), {"en"})
                self.assertEqual(set(item["specs"]["imageProducts"]), {"en"})
                self.assertIn("ko", item["specs"]["names"])

    def test_number_collision_changed_image_duplicate_locale_and_untranslated_fallback_are_not_korean(self):
        rows = [printing(i, f"Fixture {i}", i) for i in range(1,6)]
        en = [official(v,v["name"],i) for i,v in enumerate(rows,1)]
        ko = [official(v,"예시",i+10) for i,v in enumerate(rows,1)]
        rows.append({**rows[0], "printing_id": "another-finish"})
        en[1]["cardImage"]["url"] = asset(999)
        ko.append(ko[2])
        ko[3]["name"] = "Unreleased"
        ko[3]["text"]["richText"]["body"] = "English text."
        ko[4]["set"]["value"]["id"] = "OTHER"
        with tempfile.TemporaryDirectory() as tmp:
            records = list(riftbound(Fixture(Path(tmp),rows,en,ko)))
            self.assertEqual(len(records), 6)
            self.assertTrue(all("names" not in r["specs"] for r in records))
            self.assertTrue(all("_deferred_riot_edition" not in r for r in records))

    def test_missing_or_partial_edition_is_deferred_and_429_goes_to_the_existing_scheduler(self):
        a, b = printing(1,"First",1), printing(2,"Second",2)
        with tempfile.TemporaryDirectory() as tmp:
            http = Fixture(Path(tmp), [a,b], [official(a,"First",1),official(b,"Second",2)], [official(a,"첫째",3)])
            first, missing = riftbound(http)
            self.assertEqual(first["specs"]["names"]["ko"], "첫째")
            self.assertEqual(missing["_deferred_riot_edition"]["publisherId"], "ogn-002-298")
            http.write("ko-kr", [official(a, "First", 1), official(b, "Second", 2)])
            self.assertTrue(all("_deferred_riot_edition" in row for row in riftbound(http)))
            (Path(tmp)/"robots").write_text("User-agent: *\nDisallow: /ko-kr/\n")
            http.calls.clear()
            self.assertTrue(all("_deferred_riot_edition" in r for r in riftbound(http)))
            self.assertFalse(any(url in GALLERIES.values() for url,_ in http.calls))
            original = http.get
            def limited(url, **kwargs):
                if url.endswith("/robots.txt"):
                    raise HTTPError(url,429,"Too many requests",{"Retry-After":"100"},None)
                return original(url,**kwargs)
            http.get = limited
            with self.assertRaises(HTTPError):
                list(riftbound(http))


@unittest.skipUnless(os.environ.get("TCG_TEST_DSN"), "Requires isolated PostgreSQL")
class PersistRiftEditions(unittest.TestCase):
    def test_refresh_preserves_id_moderation_and_prior_provenance_only_until_a_printing_changes(self):
        from psycopg import connect
        from tcg_worker.sync import save_cards

        card = printing(1,"Fixture, Fiery",10)
        with tempfile.TemporaryDirectory() as tmp, connect(os.environ["TCG_TEST_DSN"]) as db, db.transaction(force_rollback=True):
            sid = db.execute("SELECT id FROM feed_source WHERE provider='CATALOG' AND game_code='RIFTBOUND'").fetchone()[0]
            source = {"id":sid,"game_code":"RIFTBOUND","auto_publish":True}
            http = Fixture(Path(tmp),[card],[official(card,"Fixture",10,"Fiery")],[official(card,"용사",11,"화염","<p>한 장을 뽑는다.</p>")])
            item = next(riftbound(http))
            before = {**item,"specs":{"language":"en"}}
            self.assertEqual(save_cards(db,source,[before]),1)
            key = "catalog:RIFTBOUND:en:fixture-10"
            db.execute("UPDATE card SET status='PENDING' WHERE legacy_key=%s",(key,))
            read = lambda: db.execute("SELECT id,status,name,effect,specs FROM card WHERE legacy_key=%s",(key,)).fetchone()
            original = read()
            self.assertEqual(save_cards(db,source,[item]),0)
            refreshed = read()
            self.assertEqual(refreshed[:4],original[:4])
            self.assertEqual(refreshed[-1]["names"]["ko"],"용사, 화염")
            self.assertEqual(refreshed[-1]["images"]["ko"], asset(11) + "?accountingTag=RB")
            (Path(tmp)/"ko-kr").write_text("interrupted response")
            save_cards(db,source,list(riftbound(http)))
            self.assertEqual(read(),refreshed)
            card["imgUrl"]=asset(987)
            http = Fixture(Path(tmp),[card],[official(card,"Fixture",987,"Fiery")],[official(card,"용사",12)])
            (Path(tmp)/"ko-kr").write_text("interrupted response")
            save_cards(db,source,list(riftbound(http)))
            self.assertEqual(read()[:4],original[:4])
            self.assertNotIn("names",read()[-1])
            self.assertNotIn("images",read()[-1])
