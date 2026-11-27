import unittest

from tcg_worker.catalog_sources.rift_supplement import CODEX, RIOT, fetch_page
from tcg_worker.feeds import FetchError


def codex_row(i):
    return {"id": f"codex-{i}", "riftbound_id": f"ogn-{i:03d}-298", "set": {"set_id": "ogn"},
            "name": f"Card {i}", "collector_number": i, "tcgplayer_id":"987",
            "text":{"plain":"third-party rules"}, "media":{"image_url":"https://outside.invalid/art"}}


class RiftSupplementTest(unittest.TestCase):
    def test_pages_keep_distinct_vendor_ids_and_do_not_republish_codex_assets(self):
        def get(url, headers, limit):
            self.assertFalse(headers)
            page = 2 if "page=2&" in url else 1
            self.assertTrue(url.startswith(CODEX + "?"))
            return dict(items=[codex_row(i) for i in range((page-1)*100+1,min(101,page*100)+1)],
                        total=101,page=page,size=100,pages=2)
        first, cursor = fetch_page("RIFTCODEX", request_json=get, environ={"RIOT_API_KEY":"fake"})
        last, final = fetch_page("RIFTCODEX",cursor,request_json=get)
        self.assertEqual((len(first),cursor,len(last),final),(100,"2",1,None))
        self.assertEqual(first[0], {"id":"codex-1","number":"ogn-001-298","packCode":"OGN",
            "name":"Card 1","lang":"en","sourceUrl":CODEX+"/codex-1",
            "facts":{"collectorNumber":1,"riftboundId":"ogn-001-298","tcgplayerId":"987"}})

    def test_incomplete_or_ambiguous_page(self):
        for rows,total in (([],1),([codex_row(1)]*2,2),([dict(codex_row(1),set={"set_id":"SFD"})],1)):
            with self.subTest(total=total,rows=len(rows)), self.assertRaises(FetchError):
                fetch_page("RIFTCODEX",request_json=lambda *a:dict(items=rows,total=total,pages=1,page=1,size=100))
        with self.assertRaises(ValueError):
            fetch_page("RIFTCODEX","https://elsewhere.invalid",request_json=lambda *a:self.fail("network"))

    def test_real_codex_signature_sku(self):
        card={"id":"69c4407c9288b1e85d94de8a","riftbound_id":"unl-229*-219","collector_number":229,
              "set":{"set_id":"UNL"},"name":"Vi - Piltover Enforcer (Signature)"}
        records,_=fetch_page("RIFTCODEX",request_json=lambda *args:
            dict(items=[card],page=1,size=100,pages=1,total=1))
        self.assertEqual(records[0]["number"],"unl-229*-219")

    def test_riot_english_facts_and_key_only_on_official_host(self):
        card=dict(id="ogn-001-298",name="Blazing Scorcher",collectorNumber=1,description="Publisher text",
                  type="Unit", stats={"energy":3},media=[{"url":"https://outside.invalid/art"}])
        def call(url,headers,limit):
            self.assertEqual((url,headers),(RIOT,{"X-Riot-Token":"synthetic"}))
            return {"sets":[{"id":"OGN","cards":[card]}]}
        records,cursor=fetch_page("RIOT",request_json=call,environ={"RIOT_API_KEY":"synthetic"})
        self.assertIsNone(cursor)
        self.assertEqual(records[0]["effect"],"Publisher text")
        self.assertEqual(records[0]["facts"],{"collectorNumber":1,"type":"Unit","energy":3})
        self.assertNotIn("media",records[0])
        for env in ({},{"RIOT_API_KEY":"x\nheader"}):
            with self.assertRaises(FetchError) as caught:
                fetch_page("RIOT",request_json=lambda *a:self.fail("network"),environ=env)
            self.assertTrue(caught.exception.blocked)

    def test_provider_refusal_not_retried_or_replaced(self):
        for key in ("RIOT","RIFTCODEX"):
            calls=[]
            error=FetchError("HTTP 403",blocked=True,retry_after=7200)
            def refuse(url,headers,limit):
                calls.append(url)
                raise error
            with self.assertRaises(FetchError) as caught:
                fetch_page(key,request_json=refuse,environ={"RIOT_API_KEY":"synthetic"})
            self.assertIs(caught.exception,error)
            self.assertEqual(len(calls),1)
