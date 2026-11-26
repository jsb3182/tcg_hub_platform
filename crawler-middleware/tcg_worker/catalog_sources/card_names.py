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
                localized = {lang: printed_name(value) for lang, value in item["name"].items()
                             if lang in ("ko", "ja") and isinstance(value, str) and value.strip()}
                texts = {lang: printed_name(value) for lang, value in item.get("text", {}).items()
                         if lang in ("ko","en","ja") and isinstance(value,str) and value.strip()}
                pendulum = {lang: printed_name(value) for lang, value in item.get("pendulum_effect", {}).items()
                            if lang in ("ko","en","ja") and isinstance(value,str) and value.strip()}
                for lang, value in pendulum.items():
                    texts[lang] = value + "\n" + texts.get(lang, "")
                if localized or texts:
                    names[str(cid)] = {"names": localized, "texts": texts,
                                       "legality": item.get("limit_regulation", {})}
    if not names:
        raise ValueError("Empty localized card index")
    return names


def ygo_names(http, revision):
    repo = "DawnbrandBots/yaml-yugi"
    cache = http.root / ".ygo-printed-editions-v2.json"
    previous = {}
    if cache.is_file():
        with cache.open(encoding="utf-8") as stream:
            previous = json.load(stream)
    try:
        sha = revision(http, repo, "data/cards")
        if previous.get("revision") == sha:
            return previous["names"]
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
        return names
    except (OSError, ValueError, tarfile.TarError) as error:
        logging.getLogger(__name__).warning("Printed-name update deferred (%s)", type(error).__name__)
        return previous.get("names", {})


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
