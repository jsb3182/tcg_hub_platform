"""Import independently matched card facts from a dated NamuWiki snapshot."""
from datetime import date
import json
import hashlib
import os
from pathlib import Path
import re
from urllib.parse import parse_qs, unquote, urlsplit

from psycopg.types.json import Jsonb

SEED = Path(__file__).parent / "catalog_sources" / "wiki_data" / "namuwiki.json"


def _index_bytes(path=None):
    selected = Path(path or os.environ.get("TCG_WIKI_INDEX_FILE") or SEED)
    with selected.open("rb") as handle:
        size = os.fstat(handle.fileno()).st_size
        if size > 48 * 1024 * 1024:
            raise ValueError("Reviewed index exceeds its import size limit")
        data = handle.read(size + 1)
    if len(data) != size:
        raise ValueError("Reviewed index changed during import")
    return data


def refresh_index(db, cursor):
    """Reconcile a locally supplied, reviewed snapshot index only when its content changes."""
    data = _index_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if cursor.get("sha256") == digest:
        return {**cursor, "changed": 0}
    return {**_apply_index(db, data), "sha256": digest}


GAMES = {"YUGIOH", "POKEMON", "WEISS", "ONEPIECE", "RIFTBOUND", "NIVEL"}
NUMERIC = {"atk", "def", "level", "rank", "link", "hp", "cost", "power", "life", "soul", "hit", "energy", "might"}
CATEGORICAL = {"attribute", "race", "type", "color"}
PUBLISHERS = {
    "POKEMON": {"pokemoncard.co.kr", "www.pokemoncard.co.kr"},
    "WEISS": {"ws-tcg.com", "en.ws-tcg.com"},
    "ONEPIECE": {"www.onepiece-cardgame.kr", "www.onepiece-cardgame.com", "en.onepiece-cardgame.com"},
    "RIFTBOUND": {"riftbound.leagueoflegends.com"},
    "NIVEL": {"nivelarena.co.kr", "www.nivelarena.co.kr"},
}


def string(value, limit):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= limit or any(ord(c) < 32 for c in value):
        raise ValueError("Invalid wiki card field")
    return value.strip()


def https(value):
    url = urlsplit(string(value, 2048))
    if url.scheme != "https" or not url.hostname or url.username is not None or url.password is not None or url.port not in (None, 443):
        raise ValueError("Expected a public HTTPS source URL")
    return url


def checked(row):
    game = row["game"]
    if game not in GAMES or row.get("language", "ko") != "ko":
        raise ValueError("Unknown game or document language")
    title = string(row["title"], 255)
    url = https(row["url"])
    if url.hostname != "namu.wiki" or not url.path.startswith("/w/") or unquote(url.path[3:]) != title or url.query or url.fragment:
        raise ValueError("The document URL must identify its exact NamuWiki title")
    verified = https(row["verificationUrl"])
    https(row["snapshotUrl"])
    snapshot_date = date.fromisoformat(row["snapshotDate"])
    if snapshot_date.isoformat() != row["snapshotDate"]:
        raise ValueError("Expected an ISO snapshot date")
    offset, digest = row.get("snapshotRow"), row.get("articleSha256")
    if (offset is not None or digest is not None) and not (
        type(offset) is int and 0 <= offset <= 2147483647 and isinstance(digest, str)
        and re.fullmatch(r"[0-9a-f]{64}", digest)
    ):
        raise ValueError("Invalid snapshot row or article checksum")
    names = {lang: string(v, 320) for lang, v in row["names"].items()}
    if not names.get("ko") or not set(names) <= {"ko", "ja", "en"}:
        raise ValueError("Missing Korean card name or unexpected language")
    facts = row["facts"]
    content = row.get("textKo")
    if content is not None:
        if digest is None or not isinstance(content,str) or not 1 <= len(content.strip()) <= 8000 or not re.search("[가-힣]",content):
            raise ValueError("Expected an attributed Korean text block")
        content = content.strip()
    details = row.get("details") or {}
    if not isinstance(details,dict) or set(details)-{"traits","rulings","packs"}:
        raise ValueError("Unknown document metadata")
    for key, entries in details.items():
        if digest is None or not isinstance(entries,list) or len(entries)>64:
            raise ValueError("Expected a bounded list of attributed card metadata")
        for entry in entries:
            string(entry, 1200 if key=="rulings" else 150)
    for key, value in facts.items():
        if key in NUMERIC and type(value) is int and 0 <= value <= 99999999:
            continue
        if key in CATEGORICAL:
            string(value, 64)
            continue
        raise ValueError("Unsupported wiki card fact")
    match = row["match"]
    passcode = number = None
    if game == "YUGIOH":
        cid = str(match["cid"])
        params = parse_qs(verified.query)
        if (not re.fullmatch(r"[1-9][0-9]{0,9}", cid) or verified.hostname != "www.db.yugioh-card.com"
                or verified.path != "/yugiohdb/card_search.action" or params.get("ope") != ["2"] or params.get("cid") != [cid]):
            raise ValueError("The Konami verification link must match the card ID")
        key = "cid:" + cid
        if match.get("passcode") is not None:
            raw = str(match["passcode"])
            if not re.fullmatch(r"[0-9]{1,8}", raw) or int(raw) == 0:
                raise ValueError("Invalid card passcode")
            passcode = str(int(raw))
    else:
        key = string(match["catalogKey"], 512)
        number = string(match["number"], 128)
        if not key.startswith("catalog:" + game + ":") or not key.split(":", 2)[2]:
            raise ValueError("Expected a catalog printing from the same game")
        if verified.hostname not in PUBLISHERS[game]:
            raise ValueError("Expected this game's publisher verification URL")
        if game == "POKEMON" and key.startswith("catalog:POKEMON:ko:") and verified.path != "/cards/detail/" + key.removeprefix("catalog:POKEMON:ko:"):
            raise ValueError("The Korean publisher URL must match this Pokémon printing")
    if row.get("printingNumber"):
        facts = {**facts, "printingNumber": string(row["printingNumber"], 128)}
    return {"game_code": game, "lookup_key": key, "passcode": passcode, "printing_number": number,
            "title": title, "document_url": row["url"], "revision": string(row["revision"], 100) if row.get("revision") else None,
            "snapshot_date": row["snapshotDate"], "snapshot_url": row["snapshotUrl"], "verification_url": row["verificationUrl"],
            "names": names, "facts": facts, "snapshot_row": offset, "article_sha256": digest,
            "korean_text": content,"article_details": details}


def import_wiki_cards(db, path=None):
    return _apply_index(db, _index_bytes(path))


def _apply_index(db, data):
    rows = json.loads(data.decode("utf-8"))
    if not isinstance(rows, list) or not rows:
        raise ValueError("Expected a nonempty list of verified wiki cards")
    records = [checked(row) for row in rows]
    if len({(r["game_code"], r["lookup_key"]) for r in records}) != len(records):
        raise ValueError("Multiple wiki entries claim the same card identity")
    changed = 0
    with db.transaction():
        for start in range(0, len(records), 250):
            changed += db.execute("""
                INSERT INTO wiki_card_document AS d(game_code,lookup_key,passcode,printing_number,title,document_url,
                    revision,snapshot_date,snapshot_url,verification_url,names,facts,snapshot_row,article_sha256,korean_text,article_details)
                SELECT r.* FROM jsonb_to_recordset(%s) AS r(game_code text,lookup_key text,passcode text,printing_number text,
                    title text,document_url text,revision text,snapshot_date date,snapshot_url text,verification_url text,
                    names jsonb,facts jsonb,snapshot_row integer,article_sha256 text,korean_text text,article_details jsonb)
                ON CONFLICT(game_code,lookup_key) DO UPDATE SET
                    (passcode,printing_number,title,document_url,revision,snapshot_date,snapshot_url,verification_url,names,facts,snapshot_row,article_sha256,korean_text,article_details)=
                    (excluded.passcode,excluded.printing_number,excluded.title,excluded.document_url,excluded.revision,
                     excluded.snapshot_date,excluded.snapshot_url,excluded.verification_url,excluded.names,excluded.facts,excluded.snapshot_row,excluded.article_sha256,
                     excluded.korean_text,excluded.article_details)
                WHERE excluded.snapshot_date>=d.snapshot_date AND d IS DISTINCT FROM excluded
                """, (Jsonb(records[start:start+250]),)).rowcount
    return {"documents": len(records), "changed": changed}
