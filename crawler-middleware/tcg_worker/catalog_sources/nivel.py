import re
from html.parser import HTMLParser
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.robotparser import RobotFileParser


# This is the HTTP origin explicitly published by the official card list.
ORIGIN = "http://nivelarena.co.kr"
BOARD = ORIGIN + "/bbs/board.php?bo_table=cardlists"
DETAIL = ORIGIN + "/skin/board/card_list_new/get_info.php"


class Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)

    def handle_starttag(self, tag, attrs):
        if tag == "br":
            self.parts.append("\n")
        elif tag == "img":
            alt = dict(attrs).get("alt")
            if alt:
                self.parts.append(f"[{alt}]")


def as_text(fragment):
    parser = Text()
    parser.feed(fragment)
    parser.close()
    return "\n".join(" ".join(line.split()) for line in "".join(parser.parts).splitlines() if line.strip())


def parse_detail(html, ident):
    def field(tag, key, closing):
        match = re.search(rf"<{tag}\b[^>]*\bid=['\"]{key}['\"][^>]*>(.*?)</{closing}>", html, re.I | re.S)
        return as_text(match[1]) if match else ""

    name = field("h2", "subject", "h[23]")
    parts = [item.strip() for item in field("h2", "type", "h[23]").split("/")]
    if not name or len(parts) < 2 or not parts[0]:
        raise ValueError(f"Missing Nivel card details for article {ident}")
    fields = {}
    # An effect heading can occupy an entire row. Its label must end at its own cell.
    for label, value in re.findall(r"<td\s+class=['\"]h3['\"][^>]*>((?:(?!</td>).)*)</td>\s*<td[^>]*>(.*?)</td>", html, re.I | re.S):
        fields[as_text(label)] = as_text(value)
    number = parts[0]
    pack = number.partition("-")[0]
    return {"external_id": f"ko:{ident}", "pack_code": pack, "pack_name": fields.get("제품명") or pack,
            "number": number, "name": name, "original_name": name, "rarity": fields.get("레어도"),
            "effect": field("div", "content", "div") or None, "release_date": None,
            "specs": {"language": "ko", "type": parts[1], "attribute": parts[2] if len(parts) > 2 else None,
                      **{k: v for k, v in fields.items() if k not in ("효과", "제품명", "레어도")}},
            "source_url": BOARD + "&wr_id=" + ident}


def nivel(http):
    robots = RobotFileParser()
    try:
        robots.parse(http.get(ORIGIN + "/robots.txt", ttl=3600).read_text("utf-8-sig").splitlines())
    except HTTPError as exc:
        if exc.code != 404:
            raise
        exc.close()
        robots.parse([])
    agent = "TCGHub-Catalog"
    delay = max(0.5, robots.crawl_delay(agent) or 0)
    rate = robots.request_rate(agent)
    if rate:
        delay = max(delay, rate.seconds / rate.requests)
    if not robots.can_fetch(agent, BOARD) or not robots.can_fetch(agent, DETAIL):
        raise RuntimeError("Publisher robots policy disallows the Nivel catalog")
    first = http.get(BOARD, ttl=1800, delay=delay).read_text("utf-8-sig")
    total = re.search(r"([\d,]+)\s+Cards", first, re.I)
    last = re.search(r'var\s+total_page\s*=\s*"(\d+)"', first)
    if not total or not last or not 0 < int(last[1]) <= 500:
        raise ValueError("Invalid Nivel board page count")
    ids = []
    for page in range(1, int(last[1]) + 1):
        url = BOARD + f"&page={page}"
        if not robots.can_fetch(agent, url):
            raise RuntimeError("Publisher robots policy disallows a Nivel list page")
        body = first if page == 1 else http.get(url, ttl=1800, delay=delay).read_text("utf-8-sig")
        listed = re.findall(r'data-info="[^"]*?♬(\d+)"', body)
        if not listed:
            raise ValueError(f"Empty Nivel list page {page}")
        ids.extend(listed)
    if len(set(ids)) != int(total[1].replace(",", "")) or len(ids) != len(set(ids)):
        raise ValueError("Nivel listing changed during pagination, retry after the cache expires")
    for index, ident in enumerate(ids):
        post = urlencode({"bo_table": "cardlists", "wr_id": ident}).encode()
        # Historical details change rarely. A successful response is reused across interrupted runs.
        body = http.get(DETAIL, post=post, ttl=(1 if index < 40 else 30) * 86400, size=128000, delay=delay)
        yield parse_detail(body.read_text("utf-8-sig"), ident)
