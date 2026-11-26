"""Public Bandai Korea shop directory and explicitly dated event tables."""

import json
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from urllib.parse import parse_qs, urljoin, urlsplit

from bs4 import BeautifulSoup
from psycopg.types.json import Jsonb

from .feeds import FetchError, check_robots, download

KST = timezone(timedelta(hours=9))
DIRECTORY = "https://onepiece-cardgame.kr/officialshoplist.do"
STORES = "https://onepiece-cardgame.kr/api/officialstores?sido=&gungu="
EVENTS = "https://www.onepiece-cardgame.kr/events.do"
REGIONS = {
    "서울특별시": "서울",
    "부산광역시": "부산",
    "인천광역시": "인천",
    "울산광역시": "울산",
    "대구광역시": "대구",
    "대전광역시": "대전",
    "광주광역시": "광주",
    "경기도": "경기",
    "강원도": "강원",
    "강원특별자치도": "강원",
    "경상북도": "경북",
    "경상남도": "경남",
    "충청북도": "충북",
    "충청남도": "충남",
    "전라남도": "전남",
    "전라북도": "전북",
    "전북특별자치도": "전북",
    "제주특별자치도": "제주",
    "세종특별자치시": "세종",
}
DATE = re.compile(r"(\d{4})[-.](\d{1,2})[-.](\d{1,2})\s*(?:\(([월화수목금토일])\))?")
BAD = "점포 일정의 형식을 확인할 수 없습니다. 기존 자료를 유지합니다."


def shop_key(name, address):
    """Ignore typography and floor details; retain region, road and building number (including suffix)."""
    name = unicodedata.normalize("NFKC", name).casefold().replace("티씨지", "tcg")
    name = re.sub(r"[^0-9a-z가-힣]", "", name)
    address = unicodedata.normalize("NFKC", address).strip()
    words = address.split(None, 1)
    if len(words) != 2 or not name:
        return None
    road = re.match(r"(.+?(?:로|길))\s*([0-9]+(?:-[0-9]+)?)(?=$|[\s,(])", words[1])
    if not road:
        return None
    return name, REGIONS.get(words[0], words[0]) + re.sub(
        r"\s+", "", road.group(1)
    ) + ":" + road.group(2)


def public(url):
    check_robots(url)
    data, _ = download(url, limit=2_500_000)
    return data


@dataclass(frozen=True)
class Event:
    shop: tuple
    starts: datetime
    cancelled: bool


@dataclass
class Schedule:
    key: str
    cursor: dict
    more: bool = False
    shops: set | None = None
    notice: str | None = None
    title: str | None = None
    events: list | None = None
    deferred: str | None = None


def official_shops(body):
    rows = json.loads(body)
    if not isinstance(rows, list) or not rows:
        raise FetchError("공인 점포 목록을 읽을 수 없습니다.")
    result = set()
    for row in rows:
        address = next(
            (
                v.get("value")
                for v in row.get("extravars", [])
                if v.get("eid") == "address"
            ),
            None,
        )
        name = row.get("boardTitle")
        if (
            not isinstance(name, str)
            or not isinstance(address, str)
            or not address.strip()
        ):
            raise FetchError("공인 점포 주소 또는 상호가 없습니다.")
        key = shop_key(name, address)
        if key:
            result.add(key)
    if not result:
        raise FetchError("확인 가능한 공인 점포의 도로명 주소가 없습니다.")
    return result


def event_links(body):
    anchors = BeautifulSoup(body, "html.parser").select("a.item[href]")
    if not anchors:
        raise FetchError("공식 이벤트 목록을 확인할 수 없습니다.")
    result = {}
    for a in anchors:
        label = a.select_one(".tit")
        title = label.get_text(" ", strip=True) if label else ""
        url = urlsplit(urljoin(EVENTS, a["href"]))
        query = parse_qs(url.query)
        if (url.scheme, url.netloc, url.path) != (
            "https",
            "www.onepiece-cardgame.kr",
            "/events/view.do",
        ) or set(query) != {"brdno"}:
            continue
        identifiers = query["brdno"]
        if (
            len(identifiers) == 1
            and re.fullmatch("[0-9]{1,12}", identifiers[0])
            and re.search("스탠다드|플래그[쉽십]|교류회|리미티드", title)
        ):
            result[identifiers[0]] = title
    return result


def event_table(body, expected_title=None):
    """None means no public timetable. Only a fully interpreted table can withdraw absent slots."""
    soup = BeautifulSoup(body, "html.parser")
    if expected_title:
        heading = soup.select_one(".sub_p_post_detail .top_title .tit")
        if not heading or " ".join(heading.stripped_strings).strip() != expected_title:
            raise FetchError(BAD)
    result = []
    found = False
    columns = ("주소", "점포명", "개최일", "시간")
    for table in soup.select("table"):
        rows = table.select("tr")
        header = None
        for n, row in enumerate(rows):
            names = [
                re.sub(r"\s+", "", cell.get_text(strip=True))
                for cell in row.find_all(["td", "th"], recursive=False)
            ]
            if all(k in names for k in columns):
                header = [names.index(k) for k in columns]
                break
        if header is None:
            continue
        found = True
        for row in rows[n + 1 :]:
            fields = []
            erased = set()
            for index, cell in enumerate(row.find_all(["td", "th"], recursive=False)):
                original = cell.get_text(" ", strip=True)
                for deleted in cell.select("del,s,strike,[style*='line-through']"):
                    deleted.extract()
                current = cell.get_text(" ", strip=True)
                if original and not current:
                    erased.add(index)
                fields.append(current or original)
            if not any(fields):
                continue
            if max(header) >= len(fields):
                raise FetchError(BAD)
            cancelled = any(
                re.fullmatch(r"(?:행사\s*)?취소|.*\(취소\)", f) for f in fields
            )
            if erased:
                if header[2] in erased and header[3] in erased:
                    cancelled = True
                elif not cancelled:
                    raise FetchError(BAD)
            address, name, day, hour = [fields[k] for k in header]
            d = DATE.fullmatch(day.replace(" ", ""))
            t = re.fullmatch(r"(\d{1,2}):(\d{2})(?:\s*\(취소\))?", hour)
            if not d or not t or not address or not name:
                raise FetchError(BAD)
            try:
                starts = datetime(
                    *(int(v) for v in d.groups()[:3]), int(t[1]), int(t[2]), tzinfo=KST
                )
            except ValueError as exc:
                raise FetchError(BAD) from exc
            if d[4] and d[4] != "월화수목금토일"[starts.weekday()]:
                raise FetchError(BAD)
            key = shop_key(name, address)
            # Lot addresses are valid publisher rows but cannot match our road-name directory.
            if key:
                result.append(Event(key, starts, cancelled))
    if found and not result:
        raise FetchError(BAD)
    return result if found else None


def fetch(key, cursor):
    if key == "onepiece-kr-official-shops":
        return Schedule(key, {}, shops=official_shops(public(STORES)))
    if key != "onepiece-kr-events":
        raise FetchError("알 수 없는 점포 일정 출처입니다.")
    queue = cursor.get("pending", [])
    today = datetime.now(KST).date()
    active = {
        ident: record
        for ident, record in cursor.get("active", {}).items()
        if date.fromisoformat(record[1]) >= today
    }
    if not queue:
        notices = {}
        for page in (0, 1):
            url = EVENTS + "?extraValue=&page=" + str(page) + "&size=5"
            notices.update(event_links(public(url)))
        for ident, (title, _) in active.items():
            notices.setdefault(ident, title)
        queue = list(notices.items())
    if not queue:
        return Schedule(key, {"active": active})
    notice, title = queue[0]
    if not re.fullmatch("[0-9]{1,12}", notice):
        raise FetchError(BAD)
    next_cursor = {"pending": queue[1:], "active": active}
    try:
        rows = event_table(public(notice_url(notice)), title)
    except FetchError as error:
        if error.blocked or error.retry_after:
            raise
        # Retry this article when the daily index is rebuilt, including title changes.
        # Other notices in this pass can still publish fully verified timetables.
        return Schedule(
            key, next_cursor, bool(queue[1:]), notice=notice, deferred=str(error)
        )
    if rows:
        last = max(row.starts.date() for row in rows)
        if last >= today:
            active[notice] = [title, last.isoformat()]
        else:
            active.pop(notice, None)
    return Schedule(
        key,
        next_cursor,
        bool(queue[1:]),
        notice=notice,
        title=title,
        events=rows,
    )


def notice_url(ident):
    return "https://www.onepiece-cardgame.kr/events/view.do?brdno=" + ident


def save(db, sid, schedule):
    matches = defaultdict(list)
    for ident, name, address, version in db.execute(
        "select id,name,address,edit_version from store where listed for share"
    ).fetchall():
        key = shop_key(name, address)
        if key:
            matches[key].append((ident, version))
    shops = {k: v[0] for k, v in matches.items() if len(v) == 1}
    if schedule.shops is not None:
        ids = [shops[k][0] for k in schedule.shops if k in shops and shops[k][1] == 1]
        db.execute(
            """delete from store_game g using store s where g.store_id=s.id and s.edit_version=1
                      and publisher_source_id=%s and not (s.id=any(%s::bigint[]))""",
            (sid, ids),
        )
        added = 0
        for ident in ids:
            result = db.execute(
                """insert into store_game(store_id,game_code,evidence_url,checked_on,publisher_source_id)
                          values(%s,'ONEPIECE',%s,%s,%s) on conflict(store_id,game_code) do update
                          set checked_on=excluded.checked_on where store_game.publisher_source_id=excluded.publisher_source_id
                          and store_game.checked_on is distinct from excluded.checked_on returning xmax=0""",
                (ident, DIRECTORY, datetime.now(KST).date(), sid),
            ).fetchone()
            added += int(bool(result and result[0]))
        return len(schedule.shops), added
    if schedule.events is None:
        return 0, 0
    # Slots are scoped to this publisher, notice and store. A moved start retires the
    # old slot while retaining its ID (including reminders). Manual and X rows are separate.
    wanted = {}
    for event in schedule.events:
        if event.shop not in shops:
            continue
        shop, _ = shops[event.shop]
        slot = event.starts.isoformat()
        value = (
            schedule.title,
            event.starts,
            "REJECTED" if event.cancelled else "PUBLISHED",
        )
        if (shop, slot) in wanted and wanted[shop, slot] != value:
            raise FetchError(BAD)
        wanted[shop, slot] = value
    existing = db.execute(
        """select id,store_id,schedule_slot,title,starts_at,status,schedule_expected,
                          game_code,category,ends_at,owner_id from calendar_event
                          where schedule_source_id=%s and schedule_notice=%s for update""",
        (sid, schedule.notice),
    ).fetchall()
    added = 0
    for (
        ident,
        shop,
        slot,
        title,
        starts,
        status,
        expected,
        game,
        category,
        ends,
        owner,
    ) in existing:
        value = wanted.pop((shop, slot), (title, starts, "REJECTED"))
        if expected != [shop, title, int(starts.timestamp()), status] or (
            game,
            category,
            ends,
            owner,
        ) != ("ONEPIECE", "TOURNAMENT", None, None):
            continue
        new_title, new_starts, new_status = value
        baseline = [shop, new_title, int(new_starts.timestamp()), new_status]
        if expected != baseline:
            db.execute(
                "update calendar_event set title=%s,starts_at=%s,status=%s,schedule_expected=%s where id=%s",
                (new_title, new_starts, new_status, Jsonb(baseline), ident),
            )
    for (shop, slot), (title, starts, status) in wanted.items():
        if status == "REJECTED":
            continue
        db.execute(
            """insert into calendar_event(store_id,game_code,title,category,starts_at,status,
                      schedule_source_id,schedule_notice,schedule_slot,schedule_url,schedule_expected)
                      values(%s,'ONEPIECE',%s,'TOURNAMENT',%s,%s,%s,%s,%s,%s,%s)""",
            (
                shop,
                title,
                starts,
                status,
                sid,
                schedule.notice,
                slot,
                notice_url(schedule.notice),
                Jsonb([shop, title, int(starts.timestamp()), status]),
            ),
        )
        added += 1
    return len(schedule.events), added
