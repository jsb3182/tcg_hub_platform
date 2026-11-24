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


class InvalidXPage(FetchError):
    """The timeline explicitly rejected the pagination token."""


@dataclass
class Headline:
    external_id: str
    title: str
    url: str
    published: datetime | None
    summary: str | None = None


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


def x_cooldown(headers, status):
    retry = headers.get("Retry-After")
    exhausted = headers.get("x-rate-limit-remaining") == "0" or status == 429
    if not exhausted and not retry:
        return 0
    wait = backoff({"Retry-After": retry}) if retry else 0
    if exhausted:
        reset = headers.get("x-rate-limit-reset", "")
        if reset.isdigit():
            wait = max(wait, int(reset) - int(time.time()) + 1)
        if wait <= 0:
            wait = 60
    return wait


def invalid_x_page(payload):
    if not isinstance(payload, dict):
        return False
    errors = payload.get("errors")
    for entry in [payload, *(errors if isinstance(errors, list) else [])]:
        if not isinstance(entry, dict):
            continue
        explanation = " ".join(v for k in ("title", "detail", "message")
                               if isinstance(v := entry.get(k), str)).lower()
        params = entry.get("parameters")
        targets_page = (isinstance(params, dict) and "pagination_token" in params
                        or re.search(r"\bpagination[ _-]token\b", explanation))
        if targets_page and re.search(r"\b(invalid|expired|malformed|not valid)\b", explanation):
            return True
    return False


def download(url, headers=None, limit=3_000_000, *, robots_file=False, x_api=False, on_x_limit=None):
    request = Request(url, headers={"User-Agent": AGENT, **(headers or {})})
    try:
        with build_opener(SameOrigin()).open(request, timeout=15) as response:
            if x_api and on_x_limit and (wait := x_cooldown(response.headers, response.status)):
                on_x_limit(wait)
            body = response.read(limit + 1)
            if len(body) > limit:
                raise FetchError("응답이 크기 제한을 초과했습니다.")
            return body, response.headers
    except HTTPError as error:
        with error:
            code = error.code
            wait = x_cooldown(error.headers, code) if x_api else max(backoff(error.headers), 60 if code == 429 else 0)
            if x_api and wait and on_x_limit:
                on_x_limit(wait)
            if x_api and code in (400, 422):
                try:
                    problem = json.loads(error.read(16384))
                except (UnicodeError, ValueError):
                    problem = None
                if invalid_x_page(problem):
                    raise InvalidXPage("X API 페이지 토큰을 다시 설정합니다.", retry_after=wait) from None
            if error.code == 304:
                return None, error.headers
            if robots_file and error.code in (404, 410):
                return b"", error.headers
            message = {
                401: "인증 정보를 확인하세요.", 402: "API 이용 권한 또는 크레딧을 확인하세요.",
                403: "제공자가 접근을 거부했습니다.", 429: "제공자의 호출 한도에 도달했습니다.",
            }.get(code, "제공자에서 요청에 실패했습니다.")
            raise FetchError(f"HTTP {code} · {message}", blocked=code in (401, 402, 403),
                             retry_after=wait) from None
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


def headline(base, href, title, date=None, *, key=None, summary=None):
    url = urljoin(base, href or "")
    if urlsplit(url)[:2] != urlsplit(base)[:2] or not href or not title:
        return None
    text = " ".join(title.split())[:400]
    if not text:
        return None
    return Headline(key or hashlib.sha256(url.encode()).hexdigest(), text, url, date, summary)


def rss_excerpt(description):
    if not description:
        return None
    soup = BeautifulSoup(description, "html.parser")
    for node in soup.select("script,style"):
        node.decompose()
    text = " ".join(soup.get_text(" ", strip=True).split())
    if not text:
        return None
    # Keep a bounded excerpt from the publisher's feed and link to the full notice.
    if len(text) <= 220:
        return text
    cut = text[:219].rsplit(" ", 1)[0].rstrip(".,:;- ")
    return cut + "…"


def parse_news(key, body):
    base = NEWS[key]
    if key == "weiss-en":
        root = ElementTree.fromstring(body)
        for item in root.findall("./channel/item")[:40]:
            yield headline(base, item.findtext("link"), item.findtext("title"), published(item.findtext("pubDate")),
                           summary=rss_excerpt(item.findtext("description")))
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
    # A pre-excerpt Weiss cursor could otherwise get a 304 before we have imported any excerpts.
    use_validators = key != "weiss-en" or cursor.get("excerpts") == 1
    body, headers = download(url, validators(cursor) if use_validators else {})
    if body is None:
        return FeedPage([], cursor, retry_after=gap)
    items = [item for item in parse_news(key, body) if item]
    if not items:
        raise FetchError("공식 뉴스 목록에서 항목을 찾지 못했습니다. 페이지 형식을 확인하세요.")
    items.sort(key=lambda item: item.published.timestamp() if item.published else 0, reverse=True)
    checkpoint = {"etag": headers.get("ETag"), "modified": headers.get("Last-Modified")}
    if key == "weiss-en":
        checkpoint["excerpts"] = 1
    return FeedPage(items, checkpoint, retry_after=gap)


def dc_rows(body, latest, high, page):
    soup = BeautifulSoup(body.decode("utf-8-sig"), "html.parser")
    ids, items = [], {}
    for row in soup.select("tr.ub-content[data-no]"):
        number = row.get("data-no", "")
        display = row.select_one(".gall_num")
        if not re.fullmatch(r"[1-9][0-9]{0,19}", number) or (display and not display.get_text(strip=True).isdecimal()):
            continue
        post_id = int(number)
        if post_id <= latest or (high is not None and post_id > high):
            ids.append(post_id)
            continue
        anchor = row.select_one(".gall_tit a[href]")
        title = anchor.get_text(" ", strip=True) if anchor else ""
        if not title:
            raise FetchError("게시번호에 해당하는 제목이 없어 갤러리 체크포인트를 보존합니다.")
        day = row.select_one(".gall_date[title]")
        link = f"https://gall.dcinside.com/mgallery/board/view/?id=tcggame&no={number}"
        items[post_id] = Headline(number, title[:400], link, published(day.get("title") if day else None, JST))
        ids.append(post_id)
    if not ids and not (page > 1 and soup.select_one("table.gall_list tbody")):
        raise FetchError("갤러리 목록 항목을 확인할 수 없습니다.")
    return ids, items


def dc_news(key, cursor):
    if key != "tcggame":
        raise FetchError("지정된 TCG 갤러리만 지원합니다.", blocked=True)
    if os.getenv("DCINSIDE_WRITTEN_PERMISSION") != "tcggame":
        raise FetchError("디시인사이드 이용약관 제16조에 따른 사전 서면 동의가 필요합니다.", blocked=True)
    latest = int(cursor.get("latest", 0))
    high = int(cursor["high"]) if "high" in cursor else None
    # Old offset-only cursors lack continuity evidence. Replay their frozen interval.
    scan = cursor if cursor.get("scan_version") == 1 else {}
    page = int(scan.get("page", 1))
    if not 1 <= page <= 200:
        raise FetchError("유효하지 않은 갤러리 페이지 체크포인트입니다.", blocked=True)
    url = DC_LIST + (f"&page={page}" if page > 1 else "")
    gap = check_robots(url)
    body, _ = download(url)
    ids, records = dc_rows(body, latest, high, page)
    if high is None:
        high = max([latest, *records])
    items = list(records.values())
    at_floor = not ids or min(ids) <= latest
    if not latest or (page == 1 and at_floor):
        return FeedPage(items, {"latest": high}, retry_after=gap)

    # Page offsets can shift as posts are added or removed. Hash distinct IDs in descending
    # order across pages; ordinary overlap does not change the digest or double-count a post.
    boundary = int(scan.get("boundary", high + 1))
    digest = bytes.fromhex(scan.get("digest", "00" * 32))
    count = int(scan.get("count", 0))
    for post_id in sorted(records, reverse=True):
        if post_id < boundary:
            digest = hashlib.sha256(digest + str(post_id).encode("ascii")).digest()
            count += 1
            boundary = post_id
    previous = scan.get("previous")
    attempt = int(scan.get("attempt", 1))
    base = {"latest": latest, "high": high, "scan_version": 1}
    if not at_floor:
        if page >= 200:
            raise FetchError("갤러리 200페이지 한도를 넘었습니다. 이전 체크포인트를 보존합니다.", blocked=True)
        checkpoint = {**base, "page": page + 1, "digest": digest.hex(), "boundary": boundary,
                      "count": count, "previous": previous, "attempt": attempt}
        return FeedPage(items, checkpoint, more=True, retry_after=gap)
    if count == high - latest or previous == digest.hex():
        return FeedPage(items, {"latest": high}, retry_after=gap)
    # A sparse interval needs a matching second sweep. Persist each recovered page through
    # the usual moderation/dedup transaction and use the regular poll interval after churn.
    rapid = attempt < 3
    checkpoint = {**base, "previous": digest.hex(), "attempt": attempt + 1 if rapid else 1}
    return FeedPage(items, checkpoint, more=rapid, retry_after=gap if rapid else max(gap, 3600))


def x_id(value):
    return isinstance(value, str) and re.fullmatch(r"[1-9][0-9]{0,19}", value) is not None


def x_payload(raw):
    try:
        return json.loads(raw) if raw else None
    except (UnicodeError, ValueError):
        raise FetchError("X API가 올바른 JSON 응답을 반환하지 않았습니다.") from None


def x_restart(user_id, since, wait):
    # Repeat from the last completed poll. Bounded, exclusive until_id requests
    # replace the rejected opaque token; duplicate post IDs are harmless in the DB.
    return FeedPage([], {"uid": user_id, "since": since, "id_pages": True}, more=True, retry_after=wait)


def x_news(username, cursor, *, on_x_limit=None):
    if not re.fullmatch(r"[A-Za-z0-9_]{1,15}", username):
        raise FetchError("유효한 X 계정 이름이 필요합니다.", blocked=True)
    token = os.getenv("X_BEARER_TOKEN")
    if not token:
        raise FetchError("공식 X API용 X_BEARER_TOKEN이 설정되지 않았습니다.", blocked=True)
    auth = {"Authorization": "Bearer " + token}
    api = "https://api.x.com/2/users/"
    user_id = cursor.get("uid")
    if not user_id:
        raw, headers = download(api + "by/username/" + username, auth, x_api=True, on_x_limit=on_x_limit)
        lookup = x_payload(raw)
        record = lookup.get("data") if isinstance(lookup, dict) and not lookup.get("errors") else None
        user_id = record.get("id") if isinstance(record, dict) else None
        if x_id(user_id) and (floor := x_cooldown(headers, 200)):
            return FeedPage([], {**cursor, "uid": user_id}, more=True, retry_after=floor)
    if not x_id(user_id):
        raise FetchError("X API가 계정 ID를 반환하지 않았습니다.", blocked=True)
    since, until = cursor.get("since"), cursor.get("until")
    if any(value is not None and not x_id(value) for value in (since, until, cursor.get("high"), cursor.get("oldest"))):
        raise FetchError("저장된 X 게시물 번호를 확인하세요.")
    query = {"max_results": 25, "tweet.fields": "created_at", "exclude": "replies,retweets"}
    if since:
        query["since_id"] = since
    if until:
        query["until_id"] = until
    if cursor.get("page"):
        query["pagination_token"] = cursor["page"]
    try:
        raw, headers = download(api + user_id + "/tweets?" + urlencode(query), auth, x_api=True,
                                on_x_limit=on_x_limit)
    except InvalidXPage as error:
        if cursor.get("page") and since:
            return x_restart(user_id, since, error.retry_after)
        raise
    floor = x_cooldown(headers, 200)
    payload = x_payload(raw)
    if cursor.get("page") and since and invalid_x_page(payload):
        return x_restart(user_id, since, floor)
    if not isinstance(payload, dict) or payload.get("errors") or not isinstance(payload.get("meta"), dict):
        raise FetchError("X API가 타임라인을 완전히 반환하지 않았습니다.")
    meta = payload["meta"]
    posts, next_token = payload.get("data", []), meta.get("next_token")
    if not isinstance(posts, list) or (next_token is not None and (not isinstance(next_token, str) or not next_token)):
        raise FetchError("X API 타임라인 페이지 형식을 확인하세요.")
    count = meta.get("result_count")
    if ((not posts and (count != 0 or next_token or meta.get("newest_id") or meta.get("oldest_id")))
            or ("result_count" in meta and (type(count) is not int or count != len(posts)))
            or (posts and "result_count" not in meta and "newest_id" not in meta)):
        raise FetchError("X API가 불완전한 페이지를 반환했습니다. 체크포인트를 보존합니다.")
    items = []
    for post in posts:
        post_id = post.get("id") if isinstance(post, dict) else None
        if not x_id(post_id) or (since and int(post_id) <= int(since)) or (until and int(post_id) >= int(until)):
            raise FetchError("X API가 요청 범위 밖의 게시물 번호를 반환했습니다.")
        # Keep original posts on X. Classify locally and persist a link and attribution.
        text = post.get("text", "").lower()
        category = next((label for pattern, label in (
            (r"reveal|선공개|신규 카드|公開", "카드 공개"), (r"release|booster|발매|입고|発売", "발매 소식"),
            (r"tournament|championship|대회|大会", "대회 소식"),
        ) if re.search(pattern, text)), "새 게시물")
        items.append(Headline(post_id, f"@{username} · {category}", f"https://x.com/{username}/status/{post_id}",
                              published(post.get("created_at"))))
    ids = [int(item.external_id) for item in items]
    if ids and (meta.get("newest_id", str(max(ids))) != str(max(ids))
                or meta.get("oldest_id", str(min(ids))) != str(min(ids))):
        raise FetchError("X API 페이지 경계와 게시물 번호가 일치하지 않습니다.")
    high = cursor.get("high") or (str(max(ids)) if ids else since)
    # The first subscription imports the latest page. Subsequent runs finish incremental pagination.
    if since and next_token:
        continuation = {"uid": user_id, "since": since, "high": high}
        no_progress = cursor.get("oldest") and min(ids) >= int(cursor["oldest"])
        if no_progress or next_token == cursor.get("page"):
            return x_restart(user_id, since, floor)
        if cursor.get("id_pages"):
            if min(ids) <= int(since) + 1:
                return FeedPage(items, {"uid": user_id, "since": high}, retry_after=floor)
            continuation.update(id_pages=True, until=str(min(ids)))
        else:
            continuation["page"] = next_token
            if cursor.get("page"):
                continuation["oldest"] = str(min(ids))
        return FeedPage(items, continuation, more=True, retry_after=floor)
    return FeedPage(items, {"uid": user_id, "since": high}, retry_after=floor)


def fetch_feed(provider, key, cursor, *, on_x_limit=None):
    if provider == "X":
        return x_news(key, cursor, on_x_limit=on_x_limit)
    adapters = {"DCINSIDE": dc_news, "OFFICIAL_NEWS": publisher_news}
    if provider not in adapters:
        raise FetchError("지원하지 않는 수집기입니다.", blocked=True)
    return adapters[provider](key, cursor)
