"""Character readings from individually matched NamuWiki articles, scoped to a Weiss series."""
from functools import lru_cache
import json
from pathlib import Path
import re
from urllib.parse import quote


@lru_cache(maxsize=1)
def _families():
    rows = json.loads(Path(__file__).with_name("weiss_character_names.json").read_text("utf-8"))
    families = {}
    for row in rows:
        families.setdefault(row["family"], {})[row["english"]] = row
    return families


def names_for(family):
    return {name: row["korean"] for name, row in _families().get(family, {}).items()}


@lru_cache(maxsize=128)
def _name_pattern(family):
    names = sorted(_families().get(family, {}), key=len, reverse=True)
    return re.compile(r"(?<![\w-])(?:" + "|".join(map(re.escape, names)) + r")(?![\w-])") if names else None


def character_references(title, family):
    pattern = _name_pattern(family)
    if not pattern:
        return []
    if family == "CCS":
        # A series prefix on spell cards does not identify the character on that printing.
        title = title.replace("Cardcaptor Sakura", "")
    rows = _families()[family]
    return [
        {"english": name, "korean": rows[name]["korean"], "title": rows[name]["title"],
         "url": "https://namu.wiki/w/" + quote(rows[name]["title"], safe=""), "basis": "CHARACTER_READING"}
        for name in dict.fromkeys(pattern.findall(title))
    ]
