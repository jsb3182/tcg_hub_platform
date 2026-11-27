import json
from pathlib import Path
import tempfile
import unittest
from urllib.error import HTTPError

from bs4 import BeautifulSoup
from tcg_worker.catalog_sources import onepiece_rift_nivel_releases as source


class Pages:
    def __init__(self, pages):
        self.pages = pages
        self.requested = []

    def page(self, url):
        self.requested.append(url)
        return BeautifulSoup(self.pages[url], "html.parser")


class ReleaseProducts(unittest.TestCase):
    def test_published_snapshots_have_distinct_regions_sources_and_dates(self):
        rows = json.loads(source.SEED.read_text("utf-8"))
        by_key = {(r["game"], r["key"]): r for r in rows}
        self.assertEqual(len(by_key), len(rows))
        for game, key, day in [
            ("ONEPIECE", "kr-opk-15", "2026-11-27"), ("ONEPIECE", "en-op-19", "2027-03-05"),
            ("RIFTBOUND", "kr-spiritforged-kr-launch-reveal", "2026-12-11"),
            ("RIFTBOUND", "en-legacy", "2027-01-29"), ("NIVEL", "kr-sb03", "2026-12-18"),
        ]:
            self.assertEqual(by_key[game, key]["date"], day)
        self.assertNotIn("catalogCode", by_key["NIVEL", "kr-bt08"])
        self.assertIn("웨이브 투 유", by_key["NIVEL", "kr-bt08"]["catalogName"])
        self.assertNotIn("catalogName", by_key["ONEPIECE", "kr-opk-15"])

    def test_onepiece_accepts_dated_products_and_checks_product_host(self):
        def en(label, url):
            return f'''<a class="linkListColItem" href="{url}"><span class="linkListColCat">BOOSTERS</span>
                <h4 class="linkListColTitle">BOOSTER PACK -Test- [OP-35]</h4>
                <p class="linkListColDate"><span class="head">{label}</span><time datetime="2029-04-13"></time></p></a>'''
        kr = '''<a class="desc_wrap" href="products/view.do?brdno=9"><span class="cate">BOOSTERS</span>
            <span class="tit">[OPK-35] 부스터 팩 예시</span><span class="date">2029-07-01</span></a>'''
        pages = Pages({source.OP_KR: kr + kr.replace("2029-07-01","발매일 미정"), source.OP_EN: en("Release Date", "op35.html")
                       + en("Pre-Release", "op36.html") + en("Release Date", "https://elsewhere.invalid/products/op35.html")})
        out = list(source.onepiece(pages))
        self.assertEqual([(r["key"],r["date"]) for r in out], [("kr-opk-35","2029-07-01"),("en-op-35","2029-04-13")])

    def test_riot_announcement_day_is_not_the_release_day(self):
        kr = '''<a href="/ko-kr/news/announcements/example/" aria-label="테스트 대한민국 출시 안내">
            <time datetime="2028-11-05"></time><div data-testid="card-description">2028년 12월 12일 테스트가 한국에 출시됩니다</div></a>'''
        def calendar(day):
            return f'''<div data-testid="rich-text-html"><h2>2028</h2><h4>March</h4><ul>
                <li>5-7th - New Set Pre-Rift events</li><li>{day}th - New Set launch</li>
                <li>19th - Other Set Regional</li></ul></div>'''
        fresh = source.RIOT + "/en-us/news/announcements/new-roadmap/"
        pages = Pages({source.RIOT + "/ko-kr/news/": kr + kr.replace("2028년 ", "").replace("example/", "unknown/"),
                       source.ROADMAP: calendar(12), fresh: calendar(26), source.RIOT + "/en-us/news/":
                       '<a href="https://elsewhere.invalid/roadmap/" aria-label="Roadmap"></a>'
                       '<a href="/en-us/news/announcements/new-roadmap/" aria-label="New Roadmap"></a>'})
        rows = {r["key"]: r for r in source.riftbound(pages, {})}
        self.assertEqual(set(rows), {"kr-example", "en-new-set"})
        self.assertEqual(rows["kr-example"]["date"],"2028-12-12")
        self.assertEqual((rows["en-new-set"]["date"],rows["en-new-set"]["url"]),("2028-03-26",fresh))

    def test_nivel_uses_release_field_or_dated_launch_sentence(self):
        product = source.NIVEL + "booster&wr_id=45"
        notice = source.NIVEL + "notice&wr_id=88"
        def heading(title):
            return f'<h2><span class="bo_v_tit">{title}</span></h2>'
        site = {source.NIVEL+"booster":f'<a class="bo_tit" href="{product}">부스터 팩</a>',
                source.NIVEL+"notice&sca=%EC%A0%9C%ED%92%88":
                f'<div class="bo_tit"><a href="{notice}">스페셜 부스터 팩 SB15 발매 안내</a>'
                '<a href="http://elsewhere.invalid/bbs/board.php?bo_table=notice&amp;wr_id=51">부스터 팩 SB16 발매 안내</a></div>',
                product:heading("테스트 부스터 팩 BT19")+ '<table><tr><th>발매일</th><td>2029년 6월 1일</td></tr></table>',
                notice:heading("스페셜 부스터 팩 SB15 발매 안내")+
                '<time>2029-05-01</time><div id="bo_v_con">2029년 7월 1일(일) 테스트 부스터 팩이 출시됩니다!</div>'}
        rows = list(source.nivel(Pages(site)))
        self.assertEqual([(r["code"],r["date"]) for r in rows],[("BT19","2029-06-01"),("SB15","2029-07-01")])
        self.assertEqual(rows[0]["catalogName"],rows[0]["name"])
        site[notice] = heading("부스터 팩 SB15 발매 안내")+'<div id="bo_v_con">2029년 7월 1일에 대회가 열립니다.</div>'
        self.assertEqual(len(list(source.nivel(Pages(site)))),1)

    def test_robots_denial_or_service_error_is_not_an_empty_success(self):
        with tempfile.TemporaryDirectory() as temp:
            rules = Path(temp)/"robots.txt"
            rules.write_text("User-agent: *\nDisallow: /products/\n",encoding="utf8")
            class Response:
                def get(self,url,**_):
                    if url.endswith("/robots.txt"):
                        return rules
                    raise AssertionError("Unexpected product request")
            with self.assertRaisesRegex(ValueError,"robots policy"):
                source.PublisherPages(Response()).page(source.OP_EN)
            class Busy:
                def get(self,url,**_):
                    raise HTTPError(url,429,"Busy",{},None)
            with self.assertRaises(HTTPError):
                source.PublisherPages(Busy()).page(source.OP_EN)
