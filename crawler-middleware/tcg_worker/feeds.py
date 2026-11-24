"""Bounded, same-origin publisher headlines and credentialed social feeds."""
import hashlib
import json
import math
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit, urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener
from xml.etree import ElementTree

from bs4 import BeautifulSoup
from protego import Protego

AGENT = "TCGHub/1.0"
NEWS = {
    "yugioh-en": "https://www.yugioh-card.com/en/news/",
    "weiss-en": "https://en.ws-tcg.com/information/feed/",
    "pokemon-jp": "https://www.pokemon-card.com/info/",
    "nivel-kr": "https://www.gamemarket.jp/booth/blog/5657",
    "nivel-notice-kr": "http://nivelarena.co.kr/bbs/board.php?bo_table=notice",
    "riftbound-en": "https://playriftbound.com/en-us/news/",
}
DC_LIST = "https://gall.dcinside.com/mgallery/board/lists/?id=tcggame"
UTC = timezone.utc
JST = timezone(timedelta(hours=9))
_ROBOTS = {}
_LAST_ACCESS = {}


class FetchError(Exception):
    def __init__(self, message, *, blocked=False, retry_after=0):
        super().__init__(message)
        self.blocked = blocked
        self.retry_after = retry_after


@dataclass
class Headline:
    external_id: str
    title: str
    url: str
    published: datetime | None


@dataclass
class FeedPage:
    items: list[Headline]
    cursor: dict
    more: bool = False
    retry_after: int = 0


class SameOrigin(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        konami_robot = (req.full_url == "https://www.yugioh-card.com/robots.txt"
                        and newurl == "https://img.yugioh-card.com/robots.txt")
        if not konami_robot and urlsplit(newurl)[:2] != urlsplit(req.full_url)[:2]:
            raise FetchError("원본 호스트 밖으로 리디렉션되어 요청을 중단했습니다.", blocked=True)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def backoff(headers):
    value = headers.get("Retry-After", "")
    if value.isdigit():
        return int(value)
    if value:
        try:
            return max(0, int(parsedate_to_datetime(value).timestamp() - time.time()) + 1)
        except (ValueError, TypeError, OverflowError):
            pass
    reset = headers.get("x-rate-limit-reset", "")
    return max(0, int(reset) - int(time.time()) + 1) if reset.isdigit() else 0


def download(url, headers=None, limit=3_000_000, *, robots_file=False):
    request = Request(url, headers={"User-Agent": AGENT, **(headers or {})})
    try:
        with build_opener(SameOrigin()).open(request, timeout=15) as response:
            body = response.read(limit + 1)
            if len(body) > limit:
                raise FetchError("응답이 크기 제한을 초과했습니다.")
            return body, response.headers
    except HTTPError as error:
        with error:
            if error.code == 304:
                return None, error.headers
            if robots_file and error.code in (404, 410):
                return b"", error.headers
            code = error.code
            message = {
                401: "인증 정보를 확인하세요.", 402: "API 이용 권한 또는 크레딧을 확인하세요.",
                403: "제공자가 접근을 거부했습니다.", 429: "제공자의 호출 한도에 도달했습니다.",
            }.get(code, "제공자에서 요청에 실패했습니다.")
            raise FetchError(f"HTTP {code} · {message}", blocked=code in (401, 402, 403),
                             retry_after=max(backoff(error.headers), 60 if code == 429 else 0)) from None
    except (URLError, TimeoutError, OSError):
        raise FetchError("제공자에 연결할 수 없습니다. 네트워크 및 TLS 상태를 확인하세요.") from None


def check_robots(url):
    robots = urljoin(url, "/robots.txt")
    now = time.monotonic()
    if robots not in _ROBOTS or now >= _ROBOTS[robots][0]:
        body, _ = download(robots, limit=524288, robots_file=True)
        _ROBOTS[robots] = (now + 3600, Protego.parse(body.decode("utf-8", "replace")))
        _LAST_ACCESS[robots] = now
    policy = _ROBOTS[robots][1]
    if not policy.can_fetch(url, AGENT):
        raise FetchError("제공자의 robots.txt가 이 목록 자동 수집을 제한합니다.", blocked=True)
    rate = policy.request_rate(AGENT)
    gap = max(policy.crawl_delay(AGENT) or 0, rate.seconds / rate.requests if rate and rate.requests else 0)
    wait = math.ceil(_LAST_ACCESS[robots] + gap - time.monotonic())
    if wait > 0:
        raise FetchError("robots.txt가 지정한 요청 간격을 기다립니다.", retry_after=wait)
    _LAST_ACCESS[robots] = time.monotonic()
    return math.ceil(gap)


def published(value, zone=UTC):
    if not value:
        return None
    value = value.strip()
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            stamp = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            for fmt in ("%B %d, %Y", "%Y.%m.%d", "%Y/%m/%d %H:%M", "%Y/%m/%d"):
                try:
                    stamp = datetime.strptime(value, fmt)
                    break
                except ValueError:
                    continue
            else:
                return None
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=zone)


def headline(base, href, title, date=None, *, key=None):
    url = urljoin(base, href or "")
    if urlsplit(url)[:2] != urlsplit(base)[:2] or not href or not title:
        return None
    text = " ".join(title.split())[:400]
    if not text:
        return None
    return Headline(key or hashlib.sha256(url.encode()).hexdigest(), text, url, date)


def parse_news(key, body):
    base = NEWS[key]
    if key == "weiss-en":
        # Read only titles, canonical URLs and dates from the publisher's dedicated RSS feed.
        root = ElementTree.fromstring(body)
        for item in root.findall("./channel/item")[:40]:
            yield headline(base, item.findtext("link"), item.findtext("title"), published(item.findtext("pubDate")))
        return
    soup = BeautifulSoup(body.decode("utf-8-sig"), "html.parser")
    if key == "yugioh-en":
        for anchor in soup.select("li section.copy h4 a[href]"):
            day = anchor.find_parent("li").select_one("p.date")
            yield headline(base, anchor["href"], anchor.get_text(strip=True),
                           published(day.get_text(strip=True) if day else None))
    elif key == "pokemon-jp":
        for entry in soup.select("li.List_item a.List_item_inner[href]")[:40]:
            image, day = entry.select_one("img[alt]"), entry.select_one(".Date")
            if image is not None:
                title = image.get("alt", "")
                stamp = day.get_text(strip=True) if day else ""
                # Multiple releases may link to the same product landing page.
                identity = hashlib.sha256(f"{entry['href']}|{stamp}|{title}".encode()).hexdigest()
                yield headline(base, entry["href"], title, published(stamp, JST), key=identity)
    elif key == "riftbound-en":
        for entry in soup.select('a[aria-label][href*="/news/"]')[:40]:
            day = entry.find("time")
            yield headline(base, entry["href"], entry["aria-label"],
                           published(day.get("datetime") if day else None))
    elif key == "nivel-kr":
        for entry in soup.select(".itemList-child"):
            anchor, title = entry.select_one('a[href^="/blog/"]'), entry.select_one("dt.title")
            if anchor and title and re.fullmatch(r"/blog/\d+", anchor["href"]):
                day = re.search(r"\b20\d\d/\d\d?/\d\d?(?: \d\d?:\d\d)?", entry.get_text(" ", strip=True))
                yield headline(base, anchor["href"], title.get_text(" ", strip=True),
                               published(day.group() if day else None, JST))
    elif key == "nivel-notice-kr":
        for row in soup.select("tr"):
            anchor = row.select_one(".bo_tit a[href*='wr_id=']")
            day = row.select_one(".td_datetime")
            if anchor:
                yield headline(base, anchor["href"], anchor.get_text(" ", strip=True),
                               published(day.get_text(strip=True) if day else None, JST))


def validators(cursor):
    headers = {}
    for key, name in (("etag", "If-None-Match"), ("modified", "If-Modified-Since")):
        value = cursor.get(key)
        if isinstance(value, str) and len(value) <= 512 and not re.search(r"[\r\n]", value):
            headers[name] = value
    return headers


def publisher_news(key, cursor):
    if key not in NEWS:
        raise FetchError("등록되지 않은 공식 소식 출처입니다.", blocked=True)
    url = NEWS[key]
    gap = check_robots(url)
    body, headers = download(url, validators(cursor))
    if body is None:
        return FeedPage([], cursor, retry_after=gap)
    items = [item for item in parse_news(key, body) if item]
    if not items:
        raise FetchError("공식 뉴스 목록에서 항목을 찾지 못했습니다. 페이지 형식을 확인하세요.")
    items.sort(key=lambda item: item.published.timestamp() if item.published else 0, reverse=True)
    return FeedPage(items, {"etag": headers.get("ETag"), "modified": headers.get("Last-Modified")}, retry_after=gap)


def dc_news(key, cursor):
    if key != "tcggame":
        raise FetchError("지정된 TCG 갤러리만 지원합니다.", blocked=True)
    if os.getenv("DCINSIDE_WRITTEN_PERMISSION") != "tcggame":
        raise FetchError("디시인사이드 이용약관 제16조에 따른 사전 서면 동의가 필요합니다.", blocked=True)
    page = int(cursor.get("page", 1))
    url = DC_LIST + (f"&page={page}" if page > 1 else "")
    gap = check_robots(url)
    body, _ = download(url)
    soup = BeautifulSoup(body.decode("utf-8-sig"), "html.parser")
    items, ids = [], []
    latest = int(cursor.get("latest", 0))
    for row in soup.select("tr.ub-content[data-no]"):
        number = row.get("data-no", "")
        display = row.select_one(".gall_num")
        if not re.fullmatch(r"[1-9]\d{0,19}", number) or (display and not display.get_text(strip=True).isdecimal()):
            continue
        ids.append(int(number))
        anchor = row.select_one(".gall_tit a[href]")
        if not anchor or int(number) <= latest:
            continue
        day = row.select_one(".gall_date[title]")
        title = anchor.get_text(" ", strip=True)
        link = f"https://gall.dcinside.com/mgallery/board/view/?id=tcggame&no={number}"
        if title:
            items.append(Headline(number, title[:400], link, published(day.get("title") if day else None, JST)))
    if not ids and not (page > 1 and soup.select_one("table.gall_list tbody")):
        raise FetchError("갤러리 목록 항목을 확인할 수 없습니다.")
    high = int(cursor.get("high") or max([latest, *ids]))
    if latest and ids and min(ids) > latest:
        if page >= 200:
            raise FetchError("갤러리 200페이지 한도를 넘었습니다. 이전 체크포인트를 보존합니다.", blocked=True)
        return FeedPage(items, {"latest": latest, "high": high, "page": page + 1}, more=True, retry_after=gap)
    return FeedPage(items, {"latest": high}, retry_after=gap)


def x_news(username, cursor):
    if not re.fullmatch(r"[A-Za-z0-9_]{1,15}", username):
        raise FetchError("유효한 X 계정 이름이 필요합니다.", blocked=True)
    token = os.getenv("X_BEARER_TOKEN")
    if not token:
        raise FetchError("공식 X API용 X_BEARER_TOKEN이 설정되지 않았습니다.", blocked=True)
    auth = {"Authorization": "Bearer " + token}
    api = "https://api.x.com/2/users/"
    user_id = cursor.get("uid")
    if not user_id:
        raw, _ = download(api + "by/username/" + username, auth)
        user_id = json.loads(raw).get("data", {}).get("id")
    if not re.fullmatch(r"[0-9]{1,24}", str(user_id)):
        raise FetchError("X API가 계정 ID를 반환하지 않았습니다.", blocked=True)
    query = {"max_results": 25, "tweet.fields": "created_at", "exclude": "replies,retweets"}
    if cursor.get("since"):
        query["since_id"] = cursor["since"]
    if cursor.get("page"):
        query["pagination_token"] = cursor["page"]
    raw, headers = download(api + user_id + "/tweets?" + urlencode(query), auth)
    floor = backoff(headers) if headers.get("x-rate-limit-remaining") == "0" else 0
    payload = json.loads(raw)
    if payload.get("errors") or "meta" not in payload:
        raise FetchError("X API가 타임라인을 완전히 반환하지 않았습니다.")
    items = []
    for post in payload.get("data", []):
        post_id = str(post["id"])
        if not post_id.isdecimal():
            raise ValueError("Invalid X post ID")
        # Keep original posts on X. Classify locally and persist a link and attribution.
        text = post.get("text", "").lower()
        category = next((label for pattern, label in (
            (r"reveal|선공개|신규 카드|公開", "카드 공개"), (r"release|booster|발매|입고|発売", "발매 소식"),
            (r"tournament|championship|대회|大会", "대회 소식"),
        ) if re.search(pattern, text)), "새 게시물")
        items.append(Headline(post_id, f"@{username} · {category}", f"https://x.com/{username}/status/{post_id}",
                              published(post.get("created_at"))))
    meta = payload["meta"]
    high = cursor.get("high") or meta.get("newest_id") or cursor.get("since")
    if high is not None and not str(high).isdecimal():
        raise ValueError("Invalid X high-water mark")
    # The first subscription imports the latest page. Subsequent runs finish incremental pagination.
    if cursor.get("since") and meta.get("next_token"):
        return FeedPage(items, {"uid": user_id, "since": cursor["since"], "high": high,
                                "page": meta["next_token"]}, more=True, retry_after=floor)
    return FeedPage(items, {"uid": user_id, "since": high}, retry_after=floor)


def fetch_feed(provider, key, cursor):
    adapters = {"X": x_news, "DCINSIDE": dc_news, "OFFICIAL_NEWS": publisher_news}
    if provider not in adapters:
        raise FetchError("지원하지 않는 수집기입니다.", blocked=True)
    return adapters[provider](key, cursor)
