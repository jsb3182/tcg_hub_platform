"""Dated regional products, stored independently from individual card printings."""
from datetime import date
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from psycopg.types.json import Jsonb

GAMES = {"YUGIOH", "POKEMON", "WEISS", "NIVEL", "RIFTBOUND", "ONEPIECE"}
REGIONS = {"KR", "JP", "NA", "EN", "EU", "GLOBAL", "CN", "TCG"}
DATA = Path(__file__).parent / "catalog_sources" / "release_data"
YGO_SETS = "https://db.ygoprodeck.com/api/v7/cardsets.php"


def yugioh_releases(http):
    from .catalog_sources.bulk import document
    for product in document(http.get(YGO_SETS, ttl=86400, size=3_000_000)):
        name = product.get("set_name")
        code = product.get("set_code")
        if not name or not code or not product.get("tcg_date"):
            continue
        # These have separate primary North American publisher announcements.
        if (code, name.casefold().strip()) in {
            ("CORI","chaos origins"), ("LAVD","legendary arc-v decks"), ("BETB","beyond the brave"),
            ("IMPH","immortal phoenix"), ("MZMC","maze of machines"),
        }:
            continue
        key = "ygopro:" + hashlib.sha256((code + "\0" + name).encode()).hexdigest()
        yield {"game":"YUGIOH", "key":key, "code":code, "name":name, "names":{"en":name},
               "region":"TCG", "date":product["tcg_date"], "url":YGO_SETS, "catalogName":name, "catalogCode":code}


def checked(rows, game=None):
    items = {}
    for row in rows:
        identity = row["game"], row["key"], row["region"]
        if identity[0] not in GAMES or (game is not None and identity[0] != game) or identity[2] not in REGIONS:
            raise ValueError("Unknown calendar game or territory")
        if not isinstance(identity[1], str) or not 1 <= len(identity[1].strip()) <= 160:
            raise ValueError("Missing calendar product identity")
        if not isinstance(row["name"], str) or not 1 <= len(row["name"].strip()) <= 400:
            raise ValueError("Missing calendar product name")
        if date.fromisoformat(row["date"]).isoformat() != row["date"]:
            raise ValueError("Calendar requires a confirmed day")
        url = urlsplit(row["url"])
        if not url.hostname or url.username is not None or url.password is not None or (
            url.scheme != "https" and not (row["game"] == "NIVEL" and url.scheme == "http" and url.netloc == "nivelarena.co.kr")
        ):
            raise ValueError("Invalid calendar source link")
        names = row.get("names") or {}
        if not isinstance(names, dict) or any(k not in {"ko","en","ja"} or not isinstance(v,str)
                or not 1 <= len(v.strip()) <= 400 for k,v in names.items()):
            raise ValueError("Invalid localized calendar names")
        item = {**row, "names":names}
        if row["game"] == "ONEPIECE" and row["region"] == "KR":
            code = row.get("code") or ""
            product = re.fullmatch(r"(OP|ST|EB|PRB)K-(\d{2})", code)
            if product:
                item.update(catalogCode="-".join(product.groups()), catalogName=f"[{code}] {row['name']}")
        if identity in items and items[identity] != item:
            raise ValueError("Conflicting release dates or source identities")
        items[identity] = item
    return list(items.values())


def fetch(game):
    from .catalog_sources.transport import CatalogHTTP
    http = CatalogHTTP()
    with http.scan("releases-" + game):
        if game == "YUGIOH":
            result = yugioh_releases(http)
        elif game in {"POKEMON","WEISS"}:
            from .catalog_sources.pokemon_weiss_releases import load_releases
            result = load_releases(game,http)
        else:
            from .catalog_sources.onepiece_rift_nivel_releases import load_releases
            result = load_releases(game,http)
        rows = checked(result,game)
        if not rows:
            raise ValueError("Empty regional product source")
        return rows


def save(db, rows, *, seed=False):
    if not rows:
        return 0
    return db.execute("""
        WITH incoming AS MATERIALIZED (
            SELECT game AS game_code,key AS product_key,region,code,name,names,date AS release_date,
                   url AS source_url,"catalogCode" AS catalog_code,"catalogName" AS catalog_name
              FROM jsonb_to_recordset(%s) r(game text,key text,region text,code text,name text,names jsonb,
                                            date date,url text,"catalogCode" text,"catalogName" text)
        ), previous AS MATERIALIZED (
            SELECT p.id,p.game_code,p.product_key,p.region FROM product_release p
              JOIN incoming USING(game_code,product_key,region)
        ), written AS (
            INSERT INTO product_release AS p(game_code,product_key,region,code,name,names,release_date,source_url,
                                             catalog_code,catalog_name,from_seed)
            SELECT i.*,%s FROM incoming i
            ON CONFLICT(game_code,product_key,region) DO UPDATE SET code=excluded.code,name=excluded.name,
                names=excluded.names,release_date=excluded.release_date,source_url=excluded.source_url,
                catalog_code=excluded.catalog_code,catalog_name=excluded.catalog_name,from_seed=excluded.from_seed
            WHERE NOT p.manual AND (p.from_seed OR NOT excluded.from_seed) AND
                (p.code,p.name,p.names,p.release_date,p.source_url,p.catalog_code,p.catalog_name,p.from_seed)
                IS DISTINCT FROM (excluded.code,excluded.name,excluded.names,excluded.release_date,
                                  excluded.source_url,excluded.catalog_code,excluded.catalog_name,excluded.from_seed)
            RETURNING game_code,product_key,region
        )
        SELECT count(*) FROM written LEFT JOIN previous USING(game_code,product_key,region) WHERE previous.id IS NULL
    """,(Jsonb(rows),seed)).fetchone()[0]


def seed_calendar(db):
    rows = []
    for path in sorted(DATA.glob("*.json")):
        rows.extend(json.loads(path.read_text(encoding="utf-8")))
    return save(db, checked(rows), seed=True)
