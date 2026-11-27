"""Printed names for the Korean, English and Japanese editions."""
import html
import json
import logging
import os
import re
import tarfile
import tempfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

READING = re.compile(r"<(?:rt|rp)\b[^>]*>.*?</(?:rt|rp)>", re.IGNORECASE | re.DOTALL)
TAG = re.compile(r"<[^>]+>")


def printed_name(label):
    # Japanese names may contain ruby markup. Keep the printed base characters.
    return html.unescape(TAG.sub("", READING.sub("", label))).strip()


def ygo_name_archive(path):
    names = {}
    with tarfile.open(path, "r|gz") as bundle:
        for entry in bundle:
            bundle.members.clear()
            parts = PurePosixPath(entry.name).parts
            if not entry.isfile() or len(parts) != 4 or parts[1:3] != ("data", "cards") or not parts[3].endswith(".json"):
                continue
            if not 0 < entry.size <= 4_000_000:
                raise ValueError("Unexpected card metadata size")
            with bundle.extractfile(entry) as stream:
                item = json.load(stream)
            if cid := item.get("konami_id"):
                unofficial = item.get("is_translation_unofficial") or {}
                localized = {lang: printed_name(value) for lang, value in item["name"].items()
                             if lang in ("ko", "en", "ja") and isinstance(value, str) and value.strip()
                             and not unofficial.get("name", {}).get(lang)}
                texts = {lang: printed_name(value) for lang, value in item.get("text", {}).items()
                         if lang in ("ko","en","ja") and isinstance(value,str) and value.strip()
                         and not unofficial.get("text", {}).get(lang)
                         and not unofficial.get("pendulum_effect", {}).get(lang)}
                pendulum = {lang: printed_name(value) for lang, value in item.get("pendulum_effect", {}).items()
                            if lang in ("ko","en","ja") and isinstance(value,str) and value.strip()
                            and not unofficial.get("text", {}).get(lang)
                            and not unofficial.get("pendulum_effect", {}).get(lang)}
                for lang, value in pendulum.items():
                    texts[lang] = value + "\n" + texts.get(lang, "")
                if localized or texts:
                    printings = {lang: sorted({v["set_number"] for v in rows if v.get("set_number")})
                                 for lang, rows in item.get("sets", {}).items() if lang in localized}
                    edition = {"names": localized, "texts": texts, "printings": printings,
                               "file": parts[-1], "legality": item.get("limit_regulation", {})}
                    # Alternate artwork can have a distinct passcode and printing list but the same CID.
                    previous = names.get(str(cid))
                    if previous:
                        edition["alternates"] = [*previous.pop("alternates", []), previous]
                    names[str(cid)] = edition
    if not names:
        raise ValueError("Empty localized card index")
    return names


def _ygo_snapshot(cache):
    try:
        with cache.open(encoding="utf-8") as stream:
            data = json.load(stream)
        if (isinstance(data, dict) and isinstance(data.get("revision"), str)
                and re.fullmatch(r"[0-9a-f]{40}", data["revision"])
                and isinstance(data.get("names"), dict) and data["names"]
                and all(isinstance(v, dict) and {"names","texts","file","printings"} <= v.keys()
                        for v in data["names"].values())):
            return data
    except (OSError, ValueError):
        pass
    return None


def ygo_names(http, revision, legacy=None):
    repo = "DawnbrandBots/yaml-yugi"
    cache = http.root / ".ygo-printed-editions-v3.json"
    previous = _ygo_snapshot(cache)
    try:
        sha = revision(http, repo, "data/cards")
        if previous and previous["revision"] == sha:
            if legacy is not None:
                legacy.observe_yaml(sha, previous["names"])
            return previous["names"]
        # Release the old complete index before building the new one on a 6 GB phone.
        previous = None
        path = http.get(f"https://codeload.github.com/{repo}/tar.gz/{sha}", ttl=365 * 86400,
                        size=250_000_000, family="ygo-printed-editions-archive")
        names = ygo_name_archive(path)
        fd, temp = tempfile.mkstemp(dir=http.root)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as out:
                json.dump({"revision": sha, "names": names}, out, ensure_ascii=False, separators=(",", ":"))
            os.replace(temp, cache)
        finally:
            Path(temp).unlink(missing_ok=True)
        if legacy is not None:
            legacy.observe_yaml(sha, names)
        return names
    except (OSError, ValueError, tarfile.TarError, EOFError) as error:
        previous = previous or _ygo_snapshot(cache)
        if not previous:
            if legacy is not None and legacy.allow_english_bootstrap:
                logging.getLogger(__name__).warning("Printed-name update deferred; loading the first English catalog")
                return {}
            # Only the scheduler can establish that an English-only first import is safe.
            raise
        logging.getLogger(__name__).warning("Printed-name update deferred (%s)", type(error).__name__)
        return previous["names"]


def pokemon_effect(card):
    def label(value):
        if isinstance(value, dict):
            return "".join(str(value[k]) for k in ("amount", "suffix") if value.get(k) is not None)
        return str(value) if isinstance(value, (str, int)) else ""
    parts = []
    for key in ("effect", "rule_box"):
        value = card.get(key)
        for item in value if isinstance(value, list) else [value]:
            if isinstance(item, str) and item.strip():
                parts.append(item.strip())
    for item in (card.get("abilities") or []) + (card.get("attacks") or []):
        if isinstance(item, dict):
            line = " ".join(filter(None,(label(item.get(k)) for k in ("name","damage","effect"))))
            if line: parts.append(line)
    return "\n".join(dict.fromkeys(parts)) or None


def pokemon_edition(lang, card, english_art):
    image = card.get("img") or ""
    source = card.get("url")
    url = urlsplit(image)
    allowed = {"ko": ("cards.image.pokemonkorea.co.kr","/data/wmimages/"),
               "ja": ("www.pokemon-card.com","/assets/images/card_images/large/")}
    if lang == "en":
        image = english_art.get((str(card.get("set_code") or "").lower(),str(card.get("number") or "").lstrip("0") or "0",card.get("name")))
        if isinstance(image,tuple):
            image,source=image
    elif url.scheme!="https" or url.netloc!=allowed[lang][0] or not url.path.startswith(allowed[lang][1]):
        image = None
    return {k:v for k,v in {"texts":pokemon_effect(card),"images":image,"sources":card.get("url"),
                            "imageSources":source if image else None}.items() if v}


def pokemon_with_name_references(printed_rows):
    """Index attested names on the full snapshot before yielding any reference matches."""
    def key(row):
        specs = row["specs"]
        number = specs.get("pokedex_number")
        if specs.get("card_type") == "Pokémon" and type(number) is int and number > 0:
            return number, row["name"]
        return None

    def source_url(lang, value):
        if not isinstance(value, str):
            return None
        url = urlsplit(value)
        if url.scheme == "https" and ((lang == "ja" and url.netloc == "www.pokemon-card.com"
                                      and url.path.startswith("/card-search/details.php/card/")) or
                                     (lang == "en" and url.netloc == "www.pokemon.com"
                                      and url.path.startswith("/us/pokemon-tcg/pokemon-cards/")) or
                                     (lang == "en" and url.netloc == "pkmncards.com"
                                      and url.path.startswith("/card/"))):
            return value
        return None

    # A source spelling disagreement vetoes the whole group, independent of input order.
    references = {}
    with printed_rows.open(encoding="utf-8") as records:
        for line in records:
            row = json.loads(line)
            species = key(row)
            if species is None:
                continue
            specs = row["specs"]
            for lang in ("en", "ja"):
                name = specs.get("names", {}).get(lang)
                if not name:
                    continue
                identity = (*species, lang)
                source = source_url(lang, specs.get("sources", {}).get(lang))
                if identity not in references:
                    references[identity] = (name, source)
                else:
                    previous = references[identity]
                    if previous is None or previous[0] != name:
                        references[identity] = None
                    elif source and (not previous[1] or source < previous[1]):
                        references[identity] = (name, source)
        records.seek(0)
        for line in records:
            row = json.loads(line)
            specs = row["specs"]
            species = key(row)
            if species is not None:
                for lang in ("en", "ja"):
                    match = references.get((*species, lang))
                    if match and not specs.get("names", {}).get(lang):
                        name, url = match
                        specs.setdefault("referenceNames", {})[lang] = name
                        if url:
                            specs.setdefault("referenceNameUrls", {})[lang] = url
            yield row


class PokemonNames:
    """Prefer an exact regional printing, then a unique name on the provider's card fingerprint."""
    def __init__(self):
        self.prints = {}
        self.cards = {}
        self.values = {}

    def add(self, lang, card, edition=None):
        for field, groups in (("print_key", self.prints), ("card_key", self.cards)):
            key = card.get(field)
            name = card.get("name")
            if key and name:
                names = groups.setdefault(key, {})
                names[lang] = name if names.get(lang, name) == name else None
                if edition:
                    evidence=self.values.setdefault((field,key,lang),{})
                    for k,v in edition.items():
                        evidence[k] = v if evidence.get(k,v)==v else None

    def localized(self, source_name, print_key, card_key):
        result = {"ko": source_name}
        for lang in ("en", "ja"):
            for key, groups in ((print_key, self.prints), (card_key, self.cards)):
                group = groups.get(key, {})
                if group.get("ko") == source_name and group.get(lang):
                    result[lang] = group[lang]
                    break
        return result

    def editions(self, source_name, print_key, card_key):
        names = self.localized(source_name, print_key, card_key)
        result = {"names":names,"texts":{},"images":{},"sources":{},"imageSources":{}}
        for lang, name in names.items():
            for field,key,groups in (("print_key",print_key,self.prints),("card_key",card_key,self.cards)):
                group=groups.get(key,{})
                if group.get("ko")!=source_name or group.get(lang)!=name:
                    continue
                for k,v in self.values.get((field,key,lang),{}).items():
                    if v: result[k].setdefault(lang,v)
        return result
