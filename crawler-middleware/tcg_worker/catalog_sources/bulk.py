import hashlib
import json
import os
import re
import tarfile
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import quote, urlencode

from .card_names import PokemonNames, pokemon_edition, pokemon_effect, ygo_names

def document(path):
    with path.open(encoding="utf-8-sig") as stream:
        return json.load(stream)


def revision(http, repo, directory):
    params = {"per_page": 1}
    if directory:
        params["path"] = directory
    url = f"https://api.github.com/repos/{repo}/commits?" + urlencode(params)
    value = document(http.get(url, ttl=1800))[0]["sha"]
    if not re.fullmatch(r"[0-9a-f]{40}", value):
        raise ValueError(f"Invalid catalog revision for {repo}")
    return value


def selected(record, fields):
    return {key: record[key] for key in fields if record.get(key) is not None}


def pokemon_record(card, file):
    code = card.get("set_name")
    name = card["name"]
    number = str(card.get("number") or PurePosixPath(file).stem)
    # Pokémon Korea exposes a unique physical printing id even when the card number repeats.
    ident = str(card.get("ko_id") or f"{code or 'no_set'}/{PurePosixPath(file).stem}")
    specs = selected(card, ("card_type", "hp", "types", "regulation", "stage", "pokedex_number", "attacks",
                            "abilities", "weakness", "resistance", "retreat", "set_total", "author"))
    effect = pokemon_effect(card)
    return {"external_id": "ko:" + ident, "pack_code": code, "pack_name": card.get("set_full_name") or code,
            "number": number, "name": name, "original_name": name, "rarity": card.get("rarity"),
            "effect": effect or None, "release_date": None, "specs": {"language": "ko", **specs},
            "source_url": card.get("url") or "https://github.com/type-null/PTCG-database"}


def pokemon(http):
    repo = "type-null/PTCG-database"
    sha = revision(http, repo, None)
    # Check the maintained English image index weekly even if the Korean provider is unchanged.
    from datetime import date
    week = date.today().toordinal() // 7
    derived = http.root / hashlib.sha256(f"pokemon-localized-v4:{sha}:{week}".encode()).hexdigest()
    if derived.is_file():
        http.remember_revision("pokemon-korean-archive", derived)
        with derived.open(encoding="utf-8") as cache:
            for line in cache:
                yield json.loads(line)
        return
    archive = http.get(f"https://codeload.github.com/{repo}/tar.gz/{sha}", ttl=365 * 86400, size=320_000_000,
                       family="pokemon-source-archive")
    fd, temp = tempfile.mkstemp(dir=http.root, prefix=".pokemon-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as output:
            art = pokemon_english_art(http)
            for row in pokemon_archive(archive, http.root, art):
                output.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
                yield row
        os.replace(temp, derived)
        http.remember_revision("pokemon-korean-archive", derived)
    finally:
        Path(temp).unlink(missing_ok=True)


def pokemon_english_art(http):
    from .pokemon_api import english_art
    rows=document(http.get("https://api.tcgdex.net/v2/en/cards",ttl=7*86400,size=12_000_000))
    return english_art(http,revision,rows)


def pokemon_archive(archive, workdir=None, english_art=None):
    seen = set()
    names = PokemonNames()
    languages = {"data_ko": "ko", "data_en": "en", "data_jp": "ja"}
    # Keep the original Korean printing identity, regardless of the layout of overseas sets.
    # Spool records to disk while gathering short printed names instead of retaining all card text in RAM.
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8", dir=workdir) as korean:
        with tarfile.open(archive, "r|gz") as bundle:
            for entry in bundle:
                bundle.members.clear()
                parts = PurePosixPath(entry.name).parts
                if not entry.isfile() or len(parts) < 4 or parts[1] not in languages or not parts[-1].endswith(".json"):
                    continue
                if not 0 < entry.size <= 2_000_000:
                    raise ValueError("Unexpected Pokémon card file size")
                with bundle.extractfile(entry) as stream:
                    card = json.load(stream)
                lang = languages[parts[1]]
                edition=pokemon_edition(lang,card,english_art or {})
                names.add(lang, card, edition)
                if lang == "ko" and len(parts) == 4:
                    record = pokemon_record(card, parts[-1])
                    record["specs"].update({k:{"ko":v} for k,v in edition.items()})
                    if record["external_id"] not in seen:
                        seen.add(record["external_id"])
                        korean.write(json.dumps([record, card.get("print_key"), card.get("card_key")],
                                                ensure_ascii=False, separators=(",", ":")) + "\n")
        if not seen:
            raise ValueError("Pokémon Korea subtree is empty")
        korean.seek(0)
        for line in korean:
            record, print_key, card_key = json.loads(line)
            editions=names.editions(record["name"], print_key, card_key)
            for key, values in editions.items():
                record["specs"][key]={**values,**record["specs"].get(key,{})}
            yield record


def weiss(http):
    repo = "CCondeluci/WeissSchwarz-ENG-DB"
    sha = revision(http, repo, "DB")
    file = http.get(f"https://codeload.github.com/{repo}/zip/{sha}", ttl=365 * 86400, size=70_000_000,
                    family="weiss-english-archive")
    seen = set()
    with zipfile.ZipFile(file) as archive:
        for entry in archive.infolist():
            parts = PurePosixPath(entry.filename).parts
            if len(parts) != 3 or parts[1] != "DB" or not parts[2].endswith(".json"):
                continue
            if entry.file_size > 10_000_000:
                raise ValueError("Unexpected Weiss set file size")
            with archive.open(entry) as stream:
                cards = json.load(stream)
            for card in cards:
                code, name = card["code"].strip(), card["name"].strip()
                if code in seen:
                    continue
                seen.add(code)
                pack = code.rsplit("-", 1)[0]
                yield {"external_id": "en:" + code, "pack_code": pack, "pack_name": card.get("expansion") or pack,
                       "number": code, "name": name, "original_name": name, "rarity": card.get("rarity"),
                       "effect": "\n".join(card.get("ability") or []) or None, "release_date": None,
                       "specs": {"language": "en", **selected(card, ("type", "side", "color", "level", "cost",
                                                                     "power", "soul", "trigger", "attributes"))},
                       "source_url": "https://en.ws-tcg.com/cardlist/cardsearch/exec?cardno=" + quote(code, safe="")}
    if not seen:
        raise ValueError("Weiss catalog is empty")


def riftbound(http):
    result = document(http.get("https://api.rifthunt.com/bulk/cards", ttl=24 * 3600, size=16_000_000))
    sets = {row["id"]: row for row in result["sets"]}
    if not result["cards"]:
        raise ValueError("Riftbound catalog is empty")
    for card in result["cards"]:
        group = sets[card["set"]]
        name = card["name"]
        # Alternate printings can share the Riot code or numeric collector number.
        # The old source-record id is only a label for snapshots lacking both fields.
        number = card.get("riftboundId")
        if not number:
            num = card.get("num")
            number = str(num) if num is not None else card.get("id")
        yield {"external_id": "en:" + card["printing_id"], "pack_code": group["id"], "pack_name": group["name"],
               "number": number, "name": name, "original_name": name, "rarity": card.get("rarity"),
               "effect": card.get("text"), "release_date": group.get("released"),
               "specs": {"language": "en", **selected(card, ("variant", "num", "type", "supertype", "energy",
                                                               "might", "power", "domains", "tags", "cleanName", "artist", "finishes"))},
               "source_url": "https://api.rifthunt.com/cards/" + quote(card["printing_id"], safe="")}


def yugioh(http, legacy=None):
    base = "https://db.ygoprodeck.com/api/v7/"
    translations = ygo_names(http, revision, legacy)
    version = str(document(http.get(base + "checkDBVer.php", ttl=1800))[0]["database_version"])
    sets = {r["set_name"]: r for r in document(http.get(base + "cardsets.php", revision=version))}
    offset, total, seen = 0, None, set()
    while total is None or offset < total:
        url = base + "cardinfo.php?" + urlencode({"misc": "yes", "sort": "id", "num": 500, "offset": offset})
        body = document(http.get(url, revision=version, ttl=365 * 86400, size=16_000_000))
        rows = body["data"]
        if not rows or (total is not None and total != body["meta"]["total_rows"]):
            raise ValueError("YGOPRODeck catalog changed during pagination")
        total = body["meta"]["total_rows"]
        for card in rows:
            misc = (card.get("misc_info") or [{}])[0]
            printings = card.get("card_sets") or []
            if legacy is not None:
                legacy.observe_ygopro(card)
            art = next((v.get("image_url_small") for v in card.get("card_images",[])
                        if v.get("id")==card["id"] and v.get("image_url_small")==f"https://images.ygoprodeck.com/images/cards_small/{card['id']}.jpg"),None)
            if not printings and not any(key in misc for key in ("ocg_date", "tcg_date")):
                continue
            for printing in printings or [{}]:
                name = card["name"]
                local = translations.get(str(misc.get("konami_id")), {})
                number = printing.get("set_code")
                pack_name = printing.get("set_name")
                pack = sets.get(pack_name, {})
                code = pack.get("set_code") or (number.rsplit("-", 1)[0] if number else "UNASSIGNED")
                rarity = printing.get("set_rarity")
                variant = json.dumps([pack_name, number, rarity], ensure_ascii=False).encode()
                ident = f"en:{card['id']}:" + hashlib.sha256(variant).hexdigest()[:24]
                if ident in seen:
                    continue
                seen.add(ident)
                yield {"external_id": ident, "pack_code": code, "pack_name": pack_name or "수록 팩 미확인",
                       "pack_tcg_date": pack.get("tcg_date") if pack_name else None,
                       "number": number or str(card["id"]), "name": name, "original_name": name, "rarity": rarity,
                       "effect": card.get("desc"), "release_date": pack.get("tcg_date") if printing else misc.get("ocg_date") or misc.get("tcg_date"),
                       "specs": {"language": "en", "passcode": card["id"],
                                 **({"representativeArt":art} if art and misc.get("tcg_date") else {}),
                                 "names": {**local.get("names", {}), "en": name},
                                 "texts": {"en": card.get("desc") or "", **local.get("texts", {})},
                                 "legality": local.get("legality", {}),
                                 "sources": {k: "https://www.db.yugioh-card.com/yugiohdb/card_search.action?" +
                                             urlencode({"ope":2,"cid":misc["konami_id"],"request_locale":k})
                                             for k in ("ko","en","ja") if misc.get("konami_id")},
                                 **selected(card, ("type", "race", "level", "attribute", "atk", "def",
                                                   "archetype", "scale", "linkval", "linkmarkers")),
                                 **selected(misc, ("ocg_date", "tcg_date", "formats", "konami_id"))},
                       "source_url": card["ygoprodeck_url"]}
        offset += len(rows)
