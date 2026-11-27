"""Dated physical products from the North American Pokémon and Bushiroad publisher schedules."""
from datetime import date
import json
import logging
import math
import re
from urllib.error import HTTPError
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup
from protego import Protego

from ..feeds import FetchError

POKEMON_NA = "https://press.pokemon.com/en/Items/Schedule?period=All&types=3"
WEISS_EN = "https://en.ws-tcg.com/products/products-archive/"
WEISS_JP = "https://ws-tcg.com/products/"
MONTHS = "January February March April May June July August September October November December".split()
EN_TYPES = {"Booster Pack", "Trial Deck", "Premium Booster", "Extra Booster"}
JP_TYPES = {"ブースターパック", "トライアルデッキ", "プレミアムブースター", "エクストラブースター"}
POKEMON_SETS = "https://raw.githubusercontent.com/PokemonTCG/pokemon-tcg-data/master/sets/en.json"
NON_PRODUCT = re.compile(r"\b(?:contest|tournament|exhibition|showdown event|digital|online|pocket|live|simulator|sweepstakes)\b", re.I)
PHYSICAL_TYPE = re.compile(r"\b(?:booster(?:s)?|deck(?:s)?|elite trainer box|battle academy|collection box|tin(?:s)?)\b", re.I)


def _page(http, url):
    agent = "TCGHub-Catalog/1.0"
    try:
        rules = http.get(urljoin(url, "/robots.txt"), ttl=86400, size=524288).read_text("utf-8", errors="replace")
    except HTTPError as error:
        if error.code not in (404, 410):
            raise
        rules = ""
    policy = Protego.parse(rules)
    if not policy.can_fetch(url, agent):
        raise FetchError("출판사의 상품 목록 자동 수집이 제한되어 있습니다.", blocked=True)
    rate = policy.request_rate(agent)
    delay = max(policy.crawl_delay(agent) or 0, rate.seconds / rate.requests if rate and rate.requests else 0)
    if delay > 60:
        raise FetchError("출판사의 상품 목록 요청 간격을 확인해야 합니다.", retry_after=math.ceil(delay))
    return http.get(url, ttl=86400, size=1_000_000, delay=max(1, delay)).read_bytes()


def _day(value, language):
    if language == "ja":
        match = re.fullmatch(r"発売日[：:]\s*(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日(?:[(（][月火水木金土日][)）])?", value)
        if not match:
            return None
        year, month, day = map(int, match.groups())
    else:
        match = re.fullmatch(r"([A-Za-z]+) (\d{1,2}), (\d{4})", value)
        if not match or match[1] not in MONTHS:
            return None
        year, month, day = int(match[3]), MONTHS.index(match[1]) + 1, int(match[2])
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def _product(game, region, language, base, href, name, released):
    url = urlsplit(urljoin(base, href or ""))
    prefix = "/en/products/" if game == "POKEMON" else "/products/"
    slug = url.path.removeprefix(prefix).rstrip("/")
    if (not released or not name or url.scheme != "https" or url.netloc != urlsplit(base).netloc
            or not url.path.startswith(prefix) or not re.fullmatch(r"[A-Za-z0-9_-]{1,145}", slug)
            or url.query or url.fragment):
        return None
    return {"game": game, "key": region.lower() + "-" + slug.lower(), "code": None,
            "region": region, "name": name, "names": {language: name}, "date": released, "url": url.geturl()}


def _unique(rows):
    result = {}
    for row in rows:
        if row:
            if row["key"] in result and result[row["key"]] != row:
                raise ValueError("Publisher lists inconsistent dates or names for the same product")
            result[row["key"]] = row
    if not result:
        raise ValueError("No dated physical products found in publisher schedule")
    return list(result.values())


def _published_sets(http):
    try:
        path = http.get(POKEMON_SETS, ttl=7 * 86400, size=1_000_000)
        with path.open(encoding="utf-8") as stream:
            data = json.load(stream)
        return {(row["name"].casefold(), row["releaseDate"].replace("/", "-"))
                for row in data if isinstance(row, dict) and isinstance(row.get("name"), str)
                and isinstance(row.get("releaseDate"), str)}
    except (OSError, ValueError, TypeError) as error:
        logging.getLogger(__name__).warning("Optional Pokémon set-name check unavailable (%s)", type(error).__name__)
        return set()


def pokemon_schedule(body, published_sets=()):
    rows = []
    for tr in BeautifulSoup(body, "html.parser").select("tr"):
        label = tr.select_one("a.prod-name[href]")
        stamp = tr.select_one("td.td-date")
        if not label or not stamp:
            continue
        title = label.get_text(" ", strip=True)
        match = re.fullmatch(r"(?:The )?Pokémon (?:TCG|Trading Card Game): (.+)", title)
        if not match:
            continue
        name = match[1]
        released = _day(stamp.get_text(strip=True), "en")
        confirmed = (name.casefold(), released) in published_sets
        # Future series may introduce entirely new names. The publisher's "series—expansion"
        # format and labeled physical products do not require an already indexed card list.
        if NON_PRODUCT.search(name) or name == "Scarlet & Violet—Stellar Crown Showdown":
            continue
        if not (confirmed or re.search(r"\S\s*[—–]\s*\S", name) or PHYSICAL_TYPE.search(name)):
            continue
        rows.append(_product("POKEMON", "NA", "en", POKEMON_NA, label["href"], title, released))
    return _unique(rows)


def weiss_schedule(body, region):
    japanese = region == "JP"
    language, base = ("ja", WEISS_JP) if japanese else ("en", WEISS_EN)
    selector = "a.products__link[href]" if japanese else ".c-product__list a[href]"
    rows = []
    for link in BeautifulSoup(body, "html.parser").select(selector):
        label = link.select_one(".products__name" if japanese else ".c-product__ttl")
        stamp = link.select_one(".products__salesdate" if japanese else ".c-product_release-date")
        kind = link.select_one(".products__catItem" if japanese else ".c-product__category")
        if not label or not stamp or not kind:
            continue
        category = kind.get_text(" ", strip=True)
        if category not in (JP_TYPES if japanese else EN_TYPES):
            continue
        # The Japanese Latest Products block nests its date inside the title.
        for nested_date in label.select(".products__salesdate"):
            nested_date.extract()
        name = " ".join(label.stripped_strings)
        if japanese and not name.startswith(category):
            name = category + " " + name
        row = _product("WEISS", region, language, base, link["href"], name, _day(stamp.get_text(strip=True), language))
        if row and row["key"] == "en-bp-nik2" and name == "Booster Pack GODDESS OF VICTORY: NIKKE Vol.2":
            # The English printing catalog contains this exact expansion under one product code.
            row.update(code="NIK/S135", catalogCode="NIK/S135", catalogName="GODDESS OF VICTORY: NIKKE Vol.2")
        if row and row["key"] == "en-bp-5hy3" and name == "Booster Pack The Quintessential Quintuplets Movie":
            row.update(code="5HY/W101", catalogCode="5HY/W101", catalogName="The Quintessential Quintuplets Movie")
            row["names"]["ko"] = "극장판 5등분의 신부 부스터 팩"
        rows.append(row)
    return _unique(rows)


def load_releases(game, http):
    if game == "POKEMON":
        return pokemon_schedule(_page(http, POKEMON_NA), _published_sets(http))
    if game == "WEISS":
        return weiss_schedule(_page(http, WEISS_EN), "EN") + weiss_schedule(_page(http, WEISS_JP), "JP")
    raise ValueError("Unsupported product calendar")
