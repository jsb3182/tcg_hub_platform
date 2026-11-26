"""Textual editions for exact (printing number, original name) matches in the legacy import."""
import re
from itertools import chain
from urllib.parse import quote, urlsplit

from psycopg.types.json import Jsonb


class LegacyEditions:
    def __init__(self, wanted, allow_english_bootstrap=False):
        self.wanted = set(wanted)
        self.matches = {}
        self.conflicts = set()
        self.yaml_complete = False
        self.allow_english_bootstrap = allow_english_bootstrap

    @classmethod
    def from_database(cls, db, source_id=None):
        rows = db.execute("""
            SELECT DISTINCT number,original_name FROM card
             WHERE game_code='YUGIOH' AND starts_with(legacy_key,'legacy:')
               AND number IS NOT NULL AND original_name IS NOT NULL
            """).fetchall()
        empty_source = False
        if source_id is not None:
            empty_source = not db.execute("""
                SELECT EXISTS(SELECT FROM card WHERE game_code='YUGIOH'
                  AND (source_id=%s OR starts_with(legacy_key,'catalog:YUGIOH:')))
                """, (source_id,)).fetchone()[0]
        return cls(rows, allow_english_bootstrap=empty_source)

    def _add(self, key, identity, evidence):
        if key in self.conflicts:
            return
        existing = self.matches.get(key)
        if existing is None:
            self.matches[key] = (identity, evidence)
            return
        previous_id, previous = existing
        same_provider = urlsplit(previous["source_url"]).hostname == urlsplit(evidence["source_url"]).hostname
        conflicting_text = (previous["names"], previous["texts"]) != (evidence["names"], evidence["texts"])
        if previous_id != identity or (same_provider and conflicting_text):
            self.conflicts.add(key)
            del self.matches[key]
        # YAML is observed first and carries the regional source fields. Repeated
        # rarities or a second provider confirming the same ID need no duplicate.

    def observe_yaml(self, revision, cards):
        for cid, canonical in cards.items():
            for entry in chain((canonical,), canonical.get("alternates", ())):
                names = entry["names"]
                for lang, numbers in entry["printings"].items():
                    for number in numbers:
                        key = (number, names[lang])
                        if key in self.wanted:
                            url = (f"https://github.com/DawnbrandBots/yaml-yugi/blob/{revision}/data/cards/"
                                   + quote(entry["file"], safe=""))
                            self._add(key, ("cid", int(cid)), {"konami_id": int(cid), "source_url": url,
                                                              "names": names, "texts": entry["texts"]})
        self.yaml_complete = True

    def observe_ygopro(self, card):
        # Some English prize cards have no corresponding regional entry in YAML.
        # Take only the English fields provided with an explicit English printing.
        for printing in card.get("card_sets") or []:
            key = (printing.get("set_code"), card["name"])
            if key not in self.wanted or not re.search(r"-EN[0-9]+$", key[0] or ""):
                continue
            url = card.get("ygoprodeck_url", "")
            source = urlsplit(url)
            if source.scheme != "https" or source.netloc not in ("ygoprodeck.com", "www.ygoprodeck.com") or not source.path.startswith("/card/"):
                continue
            cid = (card.get("misc_info") or [{}])[0].get("konami_id")
            self._add(key, ("cid", cid) if cid else ("ygoprodeck", card["id"]),
                      {"konami_id": cid, "source_url": url, "names": {"en": card["name"]},
                       "texts": {"en": card["desc"]} if card.get("desc") else {}})

    def reconcile(self, db):
        # A missing/incomplete publisher snapshot has no authority to retract prior matches.
        # Called in the source's final transaction after every YGOPRODeck page succeeded.
        if not self.yaml_complete:
            return
        evidence = [dict(matched_number=number, matched_name=name, **value)
                    for (number, name), (_, value) in self.matches.items()]
        db.execute("""
            WITH active AS MATERIALIZED (
              SELECT c.id AS card_id,v.* FROM jsonb_to_recordset(%s::jsonb) AS v(
                matched_number text,matched_name text,names jsonb,texts jsonb,source_url text,konami_id bigint)
              JOIN card c ON c.number=v.matched_number AND c.original_name=v.matched_name
               AND c.game_code='YUGIOH' AND starts_with(c.legacy_key,'legacy:')
            ), removed AS (
              DELETE FROM legacy_card_edition e WHERE NOT EXISTS
                (SELECT FROM active a WHERE a.card_id=e.card_id)
            )
            INSERT INTO legacy_card_edition AS e(card_id,matched_number,matched_name,names,texts,source_url,konami_id)
              SELECT card_id,matched_number,matched_name,names,texts,source_url,konami_id FROM active
              ON CONFLICT(card_id) DO UPDATE SET matched_number=excluded.matched_number,
                matched_name=excluded.matched_name,names=excluded.names,texts=excluded.texts,
                source_url=excluded.source_url,konami_id=excluded.konami_id
              WHERE (e.matched_number,e.matched_name,e.names,e.texts,e.source_url,e.konami_id)
                IS DISTINCT FROM (excluded.matched_number,excluded.matched_name,excluded.names,
                                  excluded.texts,excluded.source_url,excluded.konami_id)
            """, (Jsonb(evidence),))
