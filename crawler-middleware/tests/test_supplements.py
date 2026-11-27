import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.parse import quote

from tcg_worker.supplements import fetch, korean_yugioh


class SupplementalCatalogTests(unittest.TestCase):
    def fixture(self, payloads):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        class Fixture:
            def get(self,url,**options):
                data = payloads[url]
                file = root/"response.json"
                file.write_text(json.dumps(data),encoding="utf-8")
                return file
        return Fixture()

    def test_pokemon_locales_have_independent_checkpoints(self):
        base="https://api.tcgdex.net/v2/ko/cards"
        http=self.fixture({base:[{"id":"qa-A"}],base+"/qa-A":{"id":"qa-A","localId":"1","name":"카드",
            "set":{"id":"qa","name":"검증 팩"},"attacks":[{"effect":"확인된 효과"}]}})
        rows,cursor=fetch("TCGDEX","POKEMON",None,http)
        self.assertEqual((rows[0]["effect"],rows[0]["packName"],rows[0]["lang"]),("확인된 효과","검증 팩","ko"))
        self.assertEqual(cursor,"en:0")

    def test_korean_reference_requires_matching_name_and_both_stats(self):
        db=MagicMock()
        db.execute.return_value.fetchall.return_value=[(5,"QA-1","QA","참고 카드","4444","3000","2500")]
        url="https://api.yugiohcard.kr/card/"+quote("참고 카드",safe="")
        response={"cardName":"참고 카드","cardAtk":"공격력 3000","cardDef":"수비력 2500","cardText":"참고할 효과"}
        rows,_=korean_yugioh(db,None,self.fixture({url:response}))
        self.assertEqual(rows[0]["facts"]["konamiId"],"4444")
        rejected,_=korean_yugioh(db,None,self.fixture({url:{**response,"cardDef":"수비력 200"}}))
        self.assertEqual(rejected,[])

    @patch.dict("os.environ",{"POKEWALLET_API_KEY":"test"})
    def test_wallet_page_excludes_sealed_products_and_retains_observed_finish(self):
        base="https://api.pokewallet.io/sets"
        item={"name":"검증용 판본","product_type":"card","card_number":"001","rarity":"Rare"}
        group={"set_id":"10","name":"Test set","set_code":"QA","language":"eng"}
        http=self.fixture({base:{"data":[group]},base+"/10?page=1&limit=50":{
            "set":{**group,"total_cards":75},"cards":[{"id":"a","card_info":item,"tcgplayer":{"prices":[
                {"sub_type_name":"Holo","market_price":2.75,"updated_at":"2020-09-01T00:00:00Z"}]}},
                {"id":"box","card_info":{"product_type":"sealed"}}]}})
        rows,cursor=fetch("POKEWALLET","POKEMON",None,http)
        self.assertEqual([r["id"] for r in rows],["a"])
        self.assertEqual(cursor,["10",2])
        self.assertEqual(rows[0]["prices"][0]["market"],"TCGplayer Holo")

    @patch.dict("os.environ",{"APITCG_API_KEY":"test"})
    def test_api_tcg_retains_pack_and_cleans_markup(self):
        url="https://api.apitcg.com/api/products?tcg=one-piece&type=card&page=1&limit=50"
        http=self.fixture({url:{"data":[{"_id":2,"name":"Test","type":"card","tcg":{"_id":"one-piece"},
            "set":{"code":"OP00","name":"Test pack"},"attributes":{"Number":"OP00-001","Description":"<b>Draw</b>","Power":"2000"}}],"total":1}})
        rows,cursor=fetch("APITCG","ONEPIECE",None,http)
        self.assertEqual((rows[0]["packName"],rows[0]["effect"],rows[0]["facts"]["power"]),("Test pack","Draw","2000"))
        self.assertIsNone(cursor)
