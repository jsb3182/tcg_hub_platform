"""Recheck shipped card references against the published snapshot and the Korean OCG database.

Run from crawler-middleware: python tools/verify_namuwiki_yugioh.py [--limit N]
No credentials, database or article download directory are required.
"""
import argparse
import hashlib
import json
import re
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
from urllib.robotparser import RobotFileParser

from bs4 import BeautifulSoup


DEFAULT_SEED = Path(__file__).resolve().parents[1] / "tcg_worker/catalog_sources/wiki_data/namuwiki.json"
DATASET = "Bingsu/namuwiki_20210301_filtered"
REVISION = "bb6b2ea9bac5837836d38dc524d0b987d2a1fc0f"
SNAPSHOT = f"https://huggingface.co/datasets/{DATASET}/tree/{REVISION}"
KONAMI = "https://www.db.yugioh-card.com"
API = "https://db.ygoprodeck.com/api/v7/cardinfo.php"
AGENT = "TCGHub-ReferenceAudit/1.0"
ATTRIBUTES = {"빛":"LIGHT","어둠":"DARK","땅":"EARTH","물":"WATER","화염":"FIRE","바람":"WIND","신":"DIVINE"}


def fetch(url):
    return urlopen(Request(url, headers={"User-Agent": AGENT}), timeout=90)


def publisher_rules():
    rules = RobotFileParser()
    try:
        with fetch(KONAMI + "/robots.txt") as response:
            rules.parse(response.read().decode().splitlines())
    except HTTPError as error:
        if error.code != 404:
            raise
        rules.parse([])
    return rules


def wiki_rows(rows):
    titles = ["\"title\"='" + r["title"].replace("'", "''") + "'" for r in rows]
    params = {"dataset": DATASET, "split": "train", "config":"default", "where": " OR ".join(titles), "length":100}
    with fetch("https://datasets-server.huggingface.co/filter?" + urlencode(params)) as response:
        if response.headers.get("X-Revision") != REVISION:
            raise ValueError("Dataset revision differs from the reviewed revision")
        data = json.load(response)
    if data["num_rows_total"] != len(data["rows"]):
        raise ValueError("Incomplete article selection")
    return {r["row_idx"]:r["row"] for r in data["rows"] if not r["truncated_cells"]}


def publisher(page):
    soup = BeautifulSoup(page, "html.parser")
    name = soup.title.get_text().split(" | ")[0].strip() if soup.title else None
    fields = {}
    for box in soup.select(".CardText .item_box"):
        title = box.select_one(".item_box_title")
        value = box.select_one(".item_box_value")
        label = title.get_text(strip=True) if title else ""
        val = value.get_text(" ", strip=True) if value else ""
        if label in ("ATK", "DEF") and val.isdigit():
            fields[label.lower()] = int(val)
        if val in ATTRIBUTES:
            fields["attribute"] = val
        stat = re.fullmatch(r"(레벨|랭크) (\d+)", val)
        if stat:
            fields["level" if stat[1] == "레벨" else "rank"] = int(stat[2])
        race = box.select_one(".species span")
        if race:
            fields["race"] = race.get_text(strip=True)
    numbers = {n.get_text(strip=True) for n in soup.select("#update_list .card_number")}
    return name, fields, numbers


def confirm(seed, article, api, official, snapshot_url=SNAPSHOT):
    cid = int(seed["match"]["cid"])
    if (article["title"] != seed["title"] or seed["snapshotUrl"] != snapshot_url
            or seed["url"] != "https://namu.wiki/w/" + quote(article["title"], safe="")
            or hashlib.sha256(article["text"].encode()).hexdigest() != seed["articleSha256"]):
        return False
    name, printed, numbers = official
    if (name != seed["names"]["ko"] or int(api["id"]) != int(seed["match"]["passcode"])
            or not any(x.get("konami_id") == cid for x in api.get("misc_info", []))
            or api["name"] != seed["names"]["en"]):
        return False
    number = seed.get("printingNumber")
    if number and (number not in numbers or not re.search(r"(?<![A-Za-z0-9-])" + re.escape(number)
                                                         + r"(?![A-Za-z0-9-])", article["text"])):
        return False
    lines = [" ".join(line.split()) for line in article["text"].splitlines() if line.strip()]
    stats = seed["facts"]
    if not all(api.get("level" if key=="rank" else key) == value for key,value in stats.items()):
        return False
    for i, line in enumerate(lines):
        if line != "한글판 명칭 " + name:
            continue
        # Bound evidence to one individual template, so numbers in prose, manga
        # and adjacent card entries cannot be combined into another printing.
        block = []
        for item in lines[i+1:i+13]:
            if item.startswith("한글판 명칭 "):
                break
            block.append(item)
        if "영어판 명칭 " + api["name"] not in block:
            continue
        ja = seed["names"].get("ja")
        if ja and not any(label + ja in block for label in ("일어판 명칭 ","일본어판 명칭 ")):
            continue
        if "type" in stats and number:
            kind = {"Spell Card":"마법", "Trap Card":"함정"}.get(stats["type"])
            if kind and any(re.fullmatch(r"(일반|속공|장착|필드|지속|카운터) " + kind, b) for b in block):
                return True
        stat = "rank" if "rank" in stats else "level"
        if not all(k in printed for k in (stat, "atk", "def", "race", "attribute")):
            continue
        if (any(printed[k] != stats.get(k) for k in (stat, "atk", "def"))
                or ATTRIBUTES.get(printed["attribute"]) != stats.get("attribute")):
            continue
        heading = ("랭크" if stat == "rank" else "레벨") + " 속성 종족 공격력 수비력"
        row = " ".join(str(printed[k]) for k in (stat, "attribute", "race", "atk", "def"))
        if any((left, right) == (heading, row) for left, right in zip(block, block[1:])):
            return True
    return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("seed", nargs="?", type=Path, default=DEFAULT_SEED)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    rows = [r for r in json.loads(args.seed.read_text("utf8")) if r["game"]=="YUGIOH"][:args.limit]
    rules = publisher_rules()
    for i in range(0,len(rows),20):
        batch = rows[i:i+20]
        articles = wiki_rows(batch)
        params = urlencode({"misc":"yes", "id":",".join(str(int(r["match"]["passcode"])) for r in batch)})
        with fetch(API + "?" + params) as response:
            cards = {int(c["id"]):c for c in json.load(response)["data"]}
        for r in batch:
            cid = int(r["match"]["cid"])
            url = f"{KONAMI}/yugiohdb/card_search.action?ope=2&cid={cid}&request_locale=ko"
            if r["verificationUrl"] != url or not rules.can_fetch(AGENT,url):
                raise ValueError(f"Unverified publisher URL for {cid}")
            time.sleep(max(1, rules.crawl_delay(AGENT) or 0))
            with fetch(url) as response:
                official = publisher(response)
            if not confirm(r, articles[r["snapshotRow"]], cards[int(r["match"]["passcode"])], official):
                raise ValueError(f"Sources disagree for {r['title']} (CID {cid})")
    print(f"Verified {len(rows)} Korean OCG card references from the 2021-03-01 snapshot.")


if __name__ == "__main__":
    main()
