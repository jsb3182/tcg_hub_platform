"""Printed names for the Korean, English and Japanese editions."""
import html
import json
import logging
import os
import re
import tarfile
import tempfile
from pathlib import Path, PurePosixPath

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
                if localized:
                    names[str(cid)] = localized
    if not names:
        raise ValueError("Empty localized card index")
    return names


def ygo_names(http, revision):
    repo = "DawnbrandBots/yaml-yugi"
    cache = http.root / ".ygo-printed-editions.json"
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


class PokemonNames:
    """Prefer an exact regional printing, then a unique name on the provider's card fingerprint."""
    def __init__(self):
        self.prints = {}
        self.cards = {}

    def add(self, lang, card):
        for field, groups in (("print_key", self.prints), ("card_key", self.cards)):
            key = card.get(field)
            name = card.get("name")
            if key and name:
                names = groups.setdefault(key, {})
                names[lang] = name if names.get(lang, name) == name else None

    def localized(self, source_name, print_key, card_key):
        result = {"ko": source_name}
        for lang in ("en", "ja"):
            for key, groups in ((print_key, self.prints), (card_key, self.cards)):
                group = groups.get(key, {})
                if group.get("ko") == source_name and group.get(lang):
                    result[lang] = group[lang]
                    break
        return result
