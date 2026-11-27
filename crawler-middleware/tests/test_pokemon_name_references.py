import json
import os
import tempfile
import unittest
from pathlib import Path

from tcg_worker.catalog_sources.card_names import pokemon_with_name_references


class PokemonNameReferenceTest(unittest.TestCase):
    def test_only_unambiguous_same_species_and_full_name_carries_a_reference(self):
        source = "https://pkmncards.com/card/pikachu-example/"
        def row(number, name, names=None, sources=None, kind="Pokémon"):
            return {"name": name, "specs": {"pokedex_number": number, "card_type": kind,
                    "names": {"ko": name, **(names or {})}, "sources": sources or {},
                    "texts": {"ko": "원문"}, "images": {"ko": "existing"}}}
        records = [row(25,"피카츄"),row(25,"피카츄 ex"),row(25,"피카츄",{"en":"Pikachu","ja":"ピカチュウ"},
                       {"en":source,"ja":"https://other.example/card/1"}),
                   row(25,"피카츄",{"ja":"別名"}),row(99,"피카츄"),row(25,"피카츄",kind="Trainer"),
                   row(25,"피카츄",{"en":"Pikachu"}),row(None,"피카츄")]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"printings"
            path.write_text("".join(json.dumps(card)+"\n" for card in records), encoding="utf-8")
            actual = [r["specs"] for r in pokemon_with_name_references(path)]
        self.assertEqual(actual[0]["referenceNames"], {"en":"Pikachu"})
        self.assertEqual(actual[0]["referenceNameUrls"], {"en":source})
        self.assertEqual(actual[0]["names"], {"ko":"피카츄"})
        self.assertEqual(actual[0]["texts"], {"ko":"원문"})
        self.assertEqual(actual[0]["images"], {"ko":"existing"})
        for index in (1,2,4,5,6,7):
            self.assertNotIn("referenceNames", actual[index])

    @unittest.skipUnless(os.environ.get("TCG_TEST_DSN"), "requires isolated PostgreSQL")
    def test_migration_upgrades_only_provider_owned_rows_with_the_same_complete_name(self):
        import psycopg
        from psycopg.types.json import Jsonb
        migration = (Path(__file__).resolve().parents[2] / "backend/src/main/resources/db/migration"
                     / "V28__pokemon_reference_names.sql")
        with psycopg.connect(os.environ["TCG_TEST_DSN"]) as db:
            db.execute("create temporary table feed_source(id int,provider text,game_code text)")
            db.execute("insert into feed_source values(1,'CATALOG','POKEMON')")
            db.execute("create temporary table card(id int,source_id int,legacy_key text,game_code text,name text,specs jsonb)")
            source = "https://pkmncards.com/card/example/"
            common = {"language":"ko","pokedex_number":25,"card_type":"Pokémon","texts":{"ko":"원문"}}
            for id_, owner, label, localized in [
                    (1,1,"피카츄",{"names":{"en":"Pikachu"},"sources":{"en":source}}),
                    (2,1,"피카츄",{}),(3,1,"피카츄 ex",{}),(4,None,"피카츄",{})]:
                db.execute("insert into card values (%s,%s,%s,'POKEMON',%s,%s)",
                           (id_,owner,f"catalog:POKEMON:ko:{id_}",label,Jsonb(common | localized)))
            db.execute(migration.read_text(encoding="utf-8"))
            changed = db.execute("select id,specs from card where specs ? 'referenceNames'").fetchall()
            self.assertEqual(changed, [(2, common | {"referenceNames":{"en":"Pikachu"}, "referenceNameUrls":{"en":source}})])
