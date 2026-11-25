"""Extract a compact Korean TCG directory from an official SEMAS quarterly ZIP."""
import argparse
import calendar
import csv
from datetime import date
import io
import json
from pathlib import Path
import re
import zipfile

PORTAL = "https://www.data.go.kr/data/15083033/fileData.do"
YUGIOH = "https://www.yugioh.co.kr/site/event_store.php?code=store"
POKEMON = "https://pokemonkorea.co.kr/pokemon_cardshop/menu"
RIFTBOUND = "https://playriftbound.com/ko-KR/events/"
HOBBY = "https://www.hobbygamemall.com/goods/goods_list.php?cateCd=001003&page=4"
CHECKED = "2026-11-25"

# Exact establishment, name and road/building. A move or rename requires new evidence.
PROFILES = {
    "MA010120220812519021": ("원주카드스페이스", "능라동길 42", {"YUGIOH": YUGIOH, "POKEMON": POKEMON+"202"}),
    "MA0101202608A0104832": ("카드웨이브강릉", "솔올로 40", {"POKEMON": POKEMON+"809"}),
    "MA010120220806671985": ("카드빌리지", "통복시장1로 29", {"YUGIOH": YUGIOH}),
    "MA0101202310A0012392": ("스카이스크레이퍼", "부일로 705", {"YUGIOH": YUGIOH}),
    "MA0101202302A0091065": ("스카이스크레이퍼", "목척8길 31", {"YUGIOH": YUGIOH}),
    "MA0101202603A0012248": ("카드엘릭서", "합성남7길 31", {"YUGIOH": YUGIOH}),
    "MA0101202502A0001241": ("듀얼스파크", "동성로2길 50-13", {"YUGIOH": YUGIOH}),
    "MA010120220805023997": ("티씨지드로우", "수영로298번길 37", {"YUGIOH": YUGIOH}),
    "MA010120220812935582": ("카드킹덤", "신촌로 254", {"YUGIOH": YUGIOH}),
    "MA010120220807486519": ("카드스퀘어", "다산로40길 51", {"YUGIOH": YUGIOH}),
    "MA0101202406A0398687": ("카드숲", "조원중앙로 13", {"YUGIOH": YUGIOH, "RIFTBOUND": RIFTBOUND+"117586446689253331"}),
    "MA0101202603A0041253": ("카드챔프", "오목로 194", {"POKEMON": POKEMON+"758"}),
    "MA0101202603A0000464": ("카드프라임", "백석로 130", {"POKEMON": POKEMON+"776"}),
    "MA0101202406A0514008": ("티씨지플레이어", "화운로 106", {"YUGIOH": YUGIOH}),
    "MA0101202509A0023125": ("티씨지아레나", "염창로 77", {"YUGIOH": YUGIOH, "RIFTBOUND": RIFTBOUND+"117545207299594342"}),
    "MA0101202211A0061851": ("티씨지팩토리", "번영로 454-1", {"YUGIOH": YUGIOH}),
    "MA010120220807014543": ("하비게임몰", "중동로254번길 104", {"WEISS": HOBBY, "NIVEL": HOBBY}),
}
HOURS = {
    "MA010120220812519021": ("월 휴무 · 화–일 12:00–22:00", POKEMON+"202"),
    "MA0101202608A0104832": ("월 휴무 · 화·목·토·일 12:00–19:00 · 수·금 12:00–21:00", POKEMON+"809"),
    "MA0101202603A0041253": ("평일·주말 12:30–21:10", POKEMON+"758"),
    "MA0101202603A0000464": ("평일·주말 13:00–21:00", POKEMON+"776"),
}
# The publisher lists a different street address from the register.
ADDRESS_CONFLICTS = {"MA010120220800050140"}
REGIONS = {"강원","경기","경남","경북","대구","대전","부산","서울","세종","울산","인천","전북","제주","충남","충북"}


def select_store(row):
    key, name, address = (row[field].strip() for field in ("상가업소번호","상호명","도로명주소"))
    if key in ADDRESS_CONFLICTS:
        return None
    profile = PROFILES.get(key)
    if profile:
        if name != profile[0] or not address.endswith(" " + profile[1]):
            return None
    elif row["상권업종소분류명"] != "장난감 소매업" or not re.search(r"tcg|티씨지|포켓몬카드", name, re.I):
        return None
    lon, lat = float(row["경도"]), float(row["위도"])
    if not (address and 124 <= lon <= 132 and 33 <= lat <= 39 and re.fullmatch(r"MA[A-Z0-9]{10,30}", key)):
        raise ValueError("Invalid coordinates or identity for a selected Korean establishment")
    branch = row["지점명"].strip()
    games = profile[2] if profile else ({"POKEMON": PORTAL} if "포켓몬카드" in name else {})
    hours = {}
    if key in HOURS:
        hours = {"text": HOURS[key][0], "url": HOURS[key][1], "checked": CHECKED}
    return {"key": key, "name": " ".join(p for p in (name, branch) if p), "address": address,
            "region": row["시도명"], "lon": lon, "lat": lat, "hours": hours, "games": games,
            "checked": CHECKED if profile else None}


def extract(archive):
    rows, months, regions = {}, set(), set()
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.infolist():
            if not member.filename.lower().endswith(".csv"):
                continue
            match = re.fullmatch(r"소상공인시장진흥공단_상가\(상권\)정보_([가-힣]+)_(20\d{4})\.csv", member.filename)
            if not match or match[1] in regions or member.file_size > 1024**3:
                raise ValueError("Unexpected or duplicate SEMAS regional file")
            regions.add(match[1])
            months.add(match[2])
            with bundle.open(member) as binary, io.TextIOWrapper(binary, encoding="utf-8-sig", newline="") as text:
                for raw in csv.DictReader(text):
                    row = select_store(raw)
                    if row:
                        if row["key"] in rows:
                            raise ValueError("Duplicate establishment ID")
                        rows[row["key"]] = row
    if len(months) != 1 or not rows or not REGIONS <= regions or not ({"광주","전남"} <= regions or "전남광주" in regions):
        raise ValueError("A complete nationwide quarterly archive is required")
    month = months.pop()
    year, quarter_end = int(month[:4]), int(month[4:])
    if quarter_end not in (3, 6, 9, 12):
        raise ValueError("Unexpected quarter")
    edition = date(year, quarter_end, calendar.monthrange(year, quarter_end)[1])
    return edition, [rows[k] for k in sorted(rows)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--json", type=Path, help="write the reviewed, compact data without connecting to PostgreSQL")
    group.add_argument("--apply", action="store_true", help="apply this complete quarter to the configured PostgreSQL database")
    args = parser.parse_args()
    edition, rows = extract(args.archive)
    if args.json:
        args.json.write_text(json.dumps({"edition": str(edition), "stores": rows}, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    if args.apply:
        from psycopg.types.json import Jsonb
        from .jobs import connect
        with connect() as db:
            db.execute("SELECT apply_semas_directory(%s,%s)", (edition, Jsonb(rows)))
    region_count = len({row["region"] for row in rows})
    print(f"{edition} · {len(rows)} stores · {region_count} regions")


if __name__ == "__main__":
    main()
