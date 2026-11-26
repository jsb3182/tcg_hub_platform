import io
import json
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import urlsplit

from tcg_worker.catalog_sources.pokemon_api import API, WEEK, backup, english_art, live, printing


def card(name="Fixture", ident="set1-1"):
    return {"id":ident,"number":"1","name":name,"set":{"id":"set1"},
            "images":{"large":"https://images.pokemontcg.io/set1/1_hires.png"}}


class Responses:
    def __init__(self,root):
        self.root=Path(root)
        self.calls=[]
        self.values={"/v2/sets":{"data":[{"id":"set1","ptcgoCode":"CODE"}],"page":1,"count":1,"totalCount":1},
                     "/v2/cards/set1-1":{"data":card()}}

    def get(self,url,**_):
        self.calls.append(url)
        value=self.values[urlsplit(url).path]
        if isinstance(value,Exception): raise value
        if isinstance(value,Path): return value
        output=self.root/"response.json"
        output.write_text(json.dumps(value),"utf8")
        return output


class PokemonAPITests(unittest.TestCase):
    def test_verified_live_print_and_alias_are_used_across_restarts(self):
        with tempfile.TemporaryDirectory() as root:
            http=Responses(root)
            expected=printing(card(),"set1")
            fallback={"sets":[],"revision":"a"*40,"rows":[expected]}
            with patch("tcg_worker.catalog_sources.pokemon_api.backup",return_value=fallback):
                for i in range(2):
                    art=english_art(http,None,[{"id":"set1-001","localId":"001","name":"Fixture",
                         "image":"https://assets.tcgdex.net/en/fixture/set1/001"}])
                    self.assertEqual(art["code","1","Fixture"],(expected[-1],API+"/cards/set1-1"))
                    self.assertNotIn(("code","1","Another"),art)
            self.assertEqual(len(http.calls),2)
            self.assertTrue(http.calls[0].startswith(API+"/sets?"))
            self.assertEqual(http.calls[1],API+"/cards/set1-1")

    def test_wrong_identity_does_not_replace_cached_observation(self):
        with tempfile.TemporaryDirectory() as root:
            http=Responses(root)
            records={"set1-1":printing(card(),"set1")}
            first=live(http,records,now=50)
            http.values["/v2/cards/set1-1"]={"data":card(name="Different")}
            next_state=live(http,records,now=50+WEEK+1)
            self.assertEqual(next_state["cards"],first["cards"])
            self.assertIsNone(printing({**card(),"images":{"large":"https://example.com/set1/1.png"}},"set1"))

    def test_retry_after_persists_and_archive_prints_survive(self):
        with tempfile.TemporaryDirectory() as root:
            http=Responses(root)
            http.values["/v2/sets"]=HTTPError(API+"/sets",429,"limit",{"Retry-After":"900000"},None)
            records={"set1-1":printing(card(),"set1")}
            first=live(http,records,now=20)
            self.assertEqual(first["next"],900020)
            live(http,records,now=50000)
            self.assertEqual(len(http.calls),1)
            fallback={"sets":[["set1","OLD"]],"revision":"c"*40,"rows":list(records.values())}
            with patch("tcg_worker.catalog_sources.pokemon_api.backup",return_value=fallback), \
                 patch("tcg_worker.catalog_sources.pokemon_api.time.time",return_value=100):
                art=english_art(http,None,[])
            self.assertEqual(art["old","1","Fixture"][0],records["set1-1"][-1])
            self.assertIn("/blob/"+"c"*40+"/",art["old","1","Fixture"][1])

    def test_maintainer_snapshot_is_checked_and_kept_on_download_failure(self):
        with tempfile.TemporaryDirectory() as root:
            http=Responses(root)
            file=Path(root)/"archive.tar.gz"
            with tarfile.open(file,"w:gz") as archive:
                for path,value in (("cards/en/set1.json",[card()]),("sets/en.json",[{"id":"set1","ptcgoCode":"SET"}])):
                    data=json.dumps(value).encode()
                    entry=tarfile.TarInfo("revision/"+path)
                    entry.size=len(data)
                    archive.addfile(entry,io.BytesIO(data))
            url="/PokemonTCG/pokemon-tcg-data/tar.gz/"
            http.values[url+"a"*40]=file
            first=backup(http,lambda *_:"a"*40)
            self.assertEqual(first["rows"],[printing(card(),"set1")])
            http.values[url+"b"*40]=OSError("offline")
            self.assertEqual(backup(http,lambda *_:"b"*40),first)
