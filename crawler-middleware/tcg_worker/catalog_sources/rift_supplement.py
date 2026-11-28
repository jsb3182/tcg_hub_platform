"""Read one bounded Riftcodex page or the official Riot English content snapshot."""
import json
import os
import re
from urllib.parse import urlencode

from ..feeds import FetchError, download
from .rift_editions import RIOT_CONTENT, publisher_image_url


CODEX = "https://api.riftcodex.com/cards"
RIOT = RIOT_CONTENT
PAGE_SIZE = 100
PACK = re.compile(r"[A-Za-z0-9]{1,16}")
IDENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
PRINT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.*-]{0,127}")  # A signature can carry a literal asterisk.


def request_provider(url, headers, limit):
    body, _ = download(url, headers, limit)
    try:
        return json.loads(body)
    except (TypeError, ValueError, UnicodeError):
        raise FetchError("리프트바운드 제공자의 JSON 응답을 읽지 못했습니다.") from None


def printing(ident, number, pack, name, source):
    if not (isinstance(ident, str) and (PRINT if source == RIOT else IDENT).fullmatch(ident)
            and isinstance(number, str) and PRINT.fullmatch(number)
            and isinstance(pack, str) and PACK.fullmatch(pack)
            and number.lower().startswith(pack.lower() + "-")
            and isinstance(name, str) and 0 < len(name.strip()) <= 500):
        raise FetchError("리프트바운드 인쇄본 식별자 또는 수록 세트를 확인할 수 없습니다.")
    return {"id": ident, "number": number.lower(), "packCode": pack.upper(), "name": name.strip(),
            "lang": "en", "sourceUrl": source, "facts": {}}


def codex_page(payload, page):
    if not isinstance(payload, dict):
        raise FetchError("Riftcodex 페이지 형식을 확인할 수 없습니다.")
    rows, pages, total = (payload.get(key) for key in ("items", "pages", "total"))
    if (not isinstance(rows, list) or type(pages) is not int or type(total) is not int
            or total < 1 or not 1 <= page <= pages <= 1000 or pages != (total + PAGE_SIZE - 1) // PAGE_SIZE
            or payload.get("page") != page or payload.get("size") != PAGE_SIZE
            or len(rows) != min(PAGE_SIZE, total - (page - 1) * PAGE_SIZE)):
        raise FetchError("Riftcodex 페이지가 불완전합니다. 현재 페이지부터 다시 확인합니다.")
    records = []
    for card in rows:
        if not isinstance(card, dict) or not isinstance(card.get("set"), dict):
            raise FetchError("Riftcodex 인쇄본에 수록 세트가 없습니다.")
        ident = card.get("id")
        record = printing(ident, card.get("riftbound_id"), card["set"].get("set_id"),
                          card.get("name"), CODEX)
        record["sourceUrl"] = CODEX + "/" + ident
        record["facts"]["riftboundId"] = record["number"]
        if type(card.get("collector_number")) is int and card["collector_number"] >= 0:
            record["facts"]["collectorNumber"] = card["collector_number"]
        if isinstance(card.get("tcgplayer_id"), str) and re.fullmatch(r"[1-9][0-9]{0,15}",card["tcgplayer_id"]):
            record["facts"]["tcgplayerId"] = card["tcgplayer_id"]
        records.append(record)
    if len({r["id"] for r in records}) != len(records):
        raise FetchError("Riftcodex 페이지의 인쇄본 ID가 중복됩니다.")
    return records, str(page + 1) if page < pages else None


def riot_snapshot(payload):
    if (not isinstance(payload, dict) or not isinstance(payload.get("sets"), list) or not payload["sets"]
            or str(payload.get("locale", "en")).lower().replace("_", "-") not in ("en", "en-us", "en-gb")):
        raise FetchError("Riot의 영문 세트 목록을 확인하지 못했습니다.")
    records = []
    for group in payload["sets"]:
        if not isinstance(group, dict) or not isinstance(group.get("cards"), list):
            raise FetchError("Riot 세트의 카드 목록이 누락되었습니다.")
        for card in group["cards"]:
            if not isinstance(card, dict):
                raise FetchError("Riot 카드 정보 형식이 바뀌었습니다.")
            ident = card.get("id")
            record = printing(ident, ident, group.get("id"), card.get("name"), RIOT)
            facts = record["facts"]
            # Published CardArtDTO and the live media array can differ. Keep only absolute
            # Riot card-file URLs; joining an undocumented relative path could select another asset.
            art = card.get("art")
            urls = [art.get("fullURL")] if isinstance(art, dict) else []
            media = card.get("media")
            if isinstance(media, list):
                urls.extend(item.get("url") for item in media if isinstance(item, dict))
            approved = list(dict.fromkeys(url for url in urls if publisher_image_url(url)))
            if 0 < len(approved) <= 16:
                facts["artUrls"] = approved
            for field in ("collectorNumber", "type", "faction", "rarity"):
                value = card.get(field)
                if type(value) is int or isinstance(value, str) and 0 < len(value) <= 160:
                    facts[field] = value
            for field in ("energy", "might", "power", "cost"):
                value = (card.get("stats") or {}).get(field)
                if type(value) is int:
                    facts[field] = value
            if isinstance(card.get("description"), str) and card["description"].strip():
                record["effect"] = card["description"].strip()
            records.append(record)
    if not records or len({r["id"] for r in records}) != len(records):
        raise FetchError("Riot 인쇄본 목록이 비었거나 중복 ID가 있습니다.")
    return records, None


def fetch_page(source_key, cursor=None, *, request_json=request_provider, environ=None):
    """Return records and the next page; failures leave the caller's checkpoint intact."""
    if source_key == "RIFTCODEX":
        if cursor is not None and not re.fullmatch(r"[1-9][0-9]{0,3}", str(cursor)):
            raise ValueError("Invalid Riftcodex page")
        page = 1 if cursor is None else int(cursor)
        if page > 1000:
            raise ValueError("Riftcodex page exceeds limit")
        url = CODEX + "?" + urlencode({"sort":"public_code","dir":1,"page":page,"size":PAGE_SIZE})
        return codex_page(request_json(url, {}, 2_000_000), page)
    if source_key != "RIOT" or cursor is not None:
        raise ValueError("Unknown Riftbound provider or cursor")
    key = (os.environ if environ is None else environ).get("RIOT_API_KEY", "")
    if not key or any(ord(c) < 33 or ord(c) > 126 for c in key):
        raise FetchError("Riot 앱 전용 API 키를 설정하세요.", blocked=True)
    return riot_snapshot(request_json(RIOT, {"X-Riot-Token":key}, 12_000_000))
