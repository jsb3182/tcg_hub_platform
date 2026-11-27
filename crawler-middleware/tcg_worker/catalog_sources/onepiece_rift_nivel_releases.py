"""Dated publisher announcements. Korean and English-market editions have separate keys."""
from calendar import month_name
from datetime import date
import json
from pathlib import Path
import re
from urllib.error import HTTPError
from urllib.parse import parse_qs, urljoin, urlsplit

from bs4 import BeautifulSoup
from protego import Protego


OP_KR = "https://www.onepiece-cardgame.kr/products.do"
OP_EN = "https://en.onepiece-cardgame.com/products/?page=1&subcategory=boosters"
RIOT = "https://playriftbound.com"
ROADMAP = RIOT + "/en-us/news/announcements/august-2026-roadmap/"
NIVEL = "http://nivelarena.co.kr/bbs/board.php?bo_table="
AGENT = "TCGHub-Catalog"
SEED = Path(__file__).with_name("release_data") / "onepiece_rift_nivel.json"
KOREAN_DATE = r"(20\d{2})년\s*(\d{1,2})월\s*(\d{1,2})일"


def text(node):
    return " ".join(node.stripped_strings) if node else ""


def dated(value):
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return None
    return date.fromisoformat(value)


class PublisherPages:
    def __init__(self, http):
        self.http = http
        self.policies = {}

    def page(self, url):
        robots = urljoin(url, "/robots.txt")
        if robots not in self.policies:
            try:
                rules = self.http.get(robots, ttl=86400, size=512_000).read_text("utf-8-sig")
            except HTTPError as error:
                if error.code not in (404, 410):
                    raise
                error.close()
                rules = ""
            self.policies[robots] = Protego.parse(rules)
        policy = self.policies[robots]
        if not policy.can_fetch(url, AGENT):
            raise ValueError("Publisher robots policy disallows the product calendar")
        rate = policy.request_rate(AGENT)
        delay = max(.5, policy.crawl_delay(AGENT) or 0, rate.seconds / rate.requests if rate and rate.requests else 0)
        file = self.http.get(url, ttl=86400, size=2_000_000, delay=delay)
        return BeautifulSoup(file.read_text("utf-8-sig"), "html.parser")


def record(game, region, key, code, name, day, url):
    return {"game": game, "key": region.lower() + "-" + key, "region": region, "code": code,
            "name": name, "names": {"ko" if region == "KR" else "en": name}, "date": day.isoformat(), "url": url}


def product_pages(pages, start, next_selector, first_page, filters):
    expected = urlsplit(start)
    url = start
    for page_number in range(first_page, first_page + 32):
        page = pages.page(url)
        yield page
        link = page.select_one(next_selector)
        if not link:
            return
        url = urljoin(start, link["href"])
        parts = urlsplit(url)
        if ((parts.scheme, parts.netloc, parts.path, parts.fragment) !=
                (expected.scheme, expected.netloc, expected.path, "") or
                parse_qs(parts.query, keep_blank_values=True) !=
                {**filters, "page": [str(page_number + 1)]}):
            raise ValueError("Unexpected One Piece product pagination link")
    raise ValueError("One Piece product index exceeds its page limit")


def korean_product_rows(page):
    for a in page.select("a.desc_wrap[href]"):
        category = text(a.select_one(".cate"))
        if category not in ("BOOSTERS", "DECKS"):
            continue
        url = urljoin(OP_KR, a["href"])
        title = re.fullmatch(r"\[([A-Z0-9-]+)\]\s*(.+)", text(a.select_one(".tit")))
        day = dated(text(a.select_one(".date")))
        if title and day and re.fullmatch(r"https://www\.onepiece-cardgame\.kr/products/view\.do\?brdno=\d+", url):
            yield {**record("ONEPIECE", "KR", title[1].lower(), title[1], title[2], day, url), "publisherCategory": category}


def english_product_rows(page):
    for a in page.select("a.linkListColItem[href]"):
        title = re.fullmatch(r".*?\s-\s*(.+?)\s*-\s*\[([A-Z0-9-]+)\]", text(a.select_one(".linkListColTitle")))
        url = urljoin(OP_EN, a["href"])
        when = a.select_one(".linkListColDate time[datetime]")
        day = dated(when["datetime"]) if when else None
        if (title and text(a.select_one(".linkListColCat")) == "BOOSTERS" and day and
                text(a.select_one(".linkListColDate .head")) == "Release Date" and
                re.fullmatch(r"https://en\.onepiece-cardgame\.com/products/[a-z0-9/_-]+(?:\.html|\.php|/)", url)):
            yield {**record("ONEPIECE", "EN", title[2].lower(), title[2], title[1], day, url), "publisherCategory": "BOOSTERS"}


def onepiece(pages):
    for page in product_pages(pages, OP_KR, "a.pagi_next[href]", 0, {"size": ["12"], "extraValue": [""]}):
        yield from korean_product_rows(page)
    for page in product_pages(pages, OP_EN, "a.pagerColNext[href]:not(.disable)", 1, {"subcategory": ["boosters"]}):
        yield from english_product_rows(page)


def roadmap_rows(page, url):
    # An event/reveal date and a Pre-Rift date must never become a product date.
    months = {name: i for i, name in enumerate(month_name) if name}
    for section in page.select('[data-testid="rich-text-html"]'):
        year = month = None
        for tag in section.find_all(["h2", "h3", "h4", "li"]):
            label = text(tag)
            if tag.name == "h2":
                year = int(label) if re.fullmatch(r"20\d\d", label) else None
                month = None
            elif tag.name in ("h3", "h4"):
                month = months.get(label)
            elif year and month:
                match = re.fullmatch(r"(\d{1,2})(?:st|nd|rd|th)\s*[-–]\s*([\w ,'’:-]+?) launch(?:es)?", label, re.I)
                if match:
                    name = match[2]
                    key = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
                    yield record("RIFTBOUND", "EN", key, None, name, date(year, month, int(match[1])), url)


def riftbound(pages, seed):
    news = RIOT + "/ko-kr/news/"
    for a in pages.page(news).select('a[href][aria-label]'):
        title = re.fullmatch(r"(.+?) (?:대한민국|한국) 출시 안내", a["aria-label"])
        if not title:
            continue
        url = urljoin(news, a["href"]).rstrip("/") + "/"
        slug = re.fullmatch(r"https://playriftbound\.com/ko-kr/news/announcements/([a-z0-9-]+)/", url)
        if not slug:
            continue
        name = title[1]
        # Require the description to name this exact set and state the Korean release.
        match = re.fullmatch(r"(?:(20\d{2})년\s*)?(\d{1,2})월\s*(\d{1,2})일\s+" + re.escape(name) +
                             r"(?:이|가) (?:한국|대한민국)에 (?:정식 )?출시됩니다[.!]?", text(a.select_one('[data-testid="card-description"]')))
        if not match:
            continue
        old = seed.get("kr-" + slug[1], {})
        if match[1]:
            day = date(*map(int, match.groups()))
        elif old and old["name"] == name:
            day = date.fromisoformat(old["date"])
            if (day.month, day.day) != tuple(map(int, match.groups()[1:])):
                continue
        else:
            continue
        yield record("RIFTBOUND", "KR", slug[1], old.get("code"), name, day, url)
    # Process the verified roadmap first. A newly linked official roadmap can revise its dates.
    yield from roadmap_rows(pages.page(ROADMAP), ROADMAP)
    news = RIOT + "/en-us/news/"
    for a in pages.page(news).select('a[href][aria-label]'):
        url = urljoin(news, a["href"]).rstrip("/") + "/"
        if (url != ROADMAP and "roadmap" in a["aria-label"].lower()
                and re.fullmatch(r"https://playriftbound\.com/en-us/news/announcements/[a-z0-9-]*roadmap[a-z0-9-]*/", url)):
            yield from roadmap_rows(pages.page(url), url)
            break


def nivel_links(page, board, selector):
    seen = set()
    for a in page.select(selector):
        url = urlsplit(urljoin(NIVEL, a["href"]))
        query = parse_qs(url.query)
        post = query.get("wr_id", [])
        if (url.scheme, url.netloc, url.path) != ("http", "nivelarena.co.kr", "/bbs/board.php"):
            continue
        if query.get("bo_table") != [board] or len(post) != 1 or not re.fullmatch(r"[0-9]{1,8}", post[0]):
            continue
        if board == "notice" and not re.search(r"(?:부스터 팩|스페셜 부스터).*발매 안내$", text(a)):
            continue
        if post[0] not in seen:
            seen.add(post[0])
            yield NIVEL + board + "&wr_id=" + post[0]
            if len(seen) == 4:
                return


def nivel(pages):
    known = set()
    products = nivel_links(pages.page(NIVEL + "booster"), "booster", "a.bo_tit[href]")
    notices = nivel_links(pages.page(NIVEL + "notice&sca=%EC%A0%9C%ED%92%88"), "notice", ".bo_tit a[href]")
    for board, links in (("booster", products), ("notice", notices)):
        for url in links:
            page = pages.page(url)
            title = text(page.select_one(".bo_v_tit"))
            code = re.search(r"\b((?:BT|SB)\d{2,3})\b", title)
            if not code or code[1] in known:
                continue
            if board == "booster":
                label = page.find("th", string=lambda s: s and s.strip() == "발매일")
                when = re.fullmatch(KOREAN_DATE, text(label.find_next_sibling("td"))) if label else None
            else:
                title = title.removesuffix(" 발매 안내").strip()
                body = text(page.select_one("#bo_v_con"))
                when = re.match(KOREAN_DATE + r"(?:\([월화수목금토일]\))?\s+[^.!?]{1,140}?(?:출시|발매)됩니다", body)
            if when:
                row = record("NIVEL", "KR", code[1].lower(), code[1], title, date(*map(int, when.groups())), url)
                if board == "booster":
                    row["catalogName"] = title
                known.add(code[1])
                yield row


def load_releases(game, http):
    seed = {r["key"]: r for r in json.loads(SEED.read_text("utf-8")) if r["game"] == game}
    pages = PublisherPages(http)
    if game == "RIFTBOUND":
        live = riftbound(pages, seed)
    else:
        live = {"ONEPIECE": onepiece, "NIVEL": nivel}[game](pages)
    rows = {}
    for row in live:
        old = seed.get(row["key"], {})
        if old.get("catalogName") and old["name"] == row["name"]:
            row["catalogName"] = old["catalogName"]
        rows[row["key"]] = row
    if not rows:
        raise ValueError(f"No dated publisher products found for {game}")
    return list(rows.values())
