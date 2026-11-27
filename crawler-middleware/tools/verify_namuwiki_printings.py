"""Verify the two supported card-table layouts in a local 2026-08-29 NamuWiki snapshot."""
import argparse
from collections import defaultdict
from contextlib import closing
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import zlib

from bs4 import BeautifulSoup

from verify_namuwiki_yugioh import DEFAULT_SEED


SNAPSHOT = "https://archive.org/details/namuwiki-data-dump-20260829"
DATE = "2026-08-29"
MAX_ARTICLE = 2 * 1024 * 1024
METADATA = {
    "source": "https://namu.wiki",
    "body_format": "zlib",
    "generated_at_iso": "2026-08-29T16:57:00",
    "variant": "md-only",
}


def table_rows(table):
    for row in table.find_all("tr"):
        if row.find_parent("table") is not table:
            continue
        cells = row.find_all(["td", "th"], recursive=False)
        if not any(cell.find("table") for cell in cells):
            yield [cell.get_text(" ", strip=True) for cell in cells]


def printing_pairs(document, game):
    pairs = set()
    for table in BeautifulSoup(document, "html.parser").find_all("table"):
        if game == "NIVEL":
            has_headers = False
            for cells in table_rows(table):
                adjacent = list(zip(cells, cells[1:]))
                if ("카드넘버", "카드명") in adjacent:
                    has_headers = True
                elif has_headers:
                    # Rowspans in the restriction column change the number's column index.
                    matches = [pair for pair in adjacent if re.fullmatch(r"[A-Z]{2}\d{2}-\d{3}", pair[0])]
                    if len(matches) == 1:
                        pairs.add(matches[0])
        elif game == "ONEPIECE":
            name = None
            headers = []
            for cells in table_rows(table):
                if cells and cells[0] == "한글판 명칭":
                    name = cells[1] if len(cells) == 2 else None
                    headers = []
                elif "카드 번호" in cells:
                    headers = cells
                elif headers:
                    if name and len(cells) == len(headers):
                        pairs.add((cells[headers.index("카드 번호")], name))
                    headers = []
        else:
            raise ValueError(f"Unsupported card-table layout: {game}")
    return pairs


def read_article(db, row_id, title, digest):
    found = db.execute(
        "SELECT title, CASE WHEN length(md) <= ? THEN md END FROM docs WHERE id = ?",
        (MAX_ARTICLE, row_id),
    ).fetchone()
    if not found or found[0] != title or not isinstance(found[1], bytes):
        raise ValueError(f"Article row, title or size mismatch at row {row_id}")
    stream = zlib.decompressobj()
    raw = stream.decompress(found[1], MAX_ARTICLE + 1)
    if len(raw) > MAX_ARTICLE or not stream.eof or stream.unused_data:
        raise ValueError(f"Invalid or oversized compressed article at row {row_id}")
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError(f"Article SHA-256 mismatch at row {row_id}")
    return raw.decode("utf-8")


def verify(db, seed):
    db.execute("PRAGMA trusted_schema=OFF")
    db.execute("PRAGMA query_only=ON")
    meta = dict(db.execute("SELECT k,v FROM meta WHERE k IN (?,?,?,?)", tuple(METADATA)))
    if meta != METADATA:
        raise ValueError("The local SQLite metadata does not match the reviewed snapshot")
    articles = defaultdict(list)
    for row in seed:
        if row["snapshotUrl"] != SNAPSHOT and row["snapshotDate"] != DATE:
            continue
        if row["snapshotUrl"] != SNAPSHOT or row["snapshotDate"] != DATE:
            raise ValueError("Inconsistent snapshot URL and date")
        key = (row["snapshotRow"], row["title"], row["articleSha256"], row["game"])
        articles[key].append(row)
    if not articles:
        raise ValueError("No reviewed card rows from the expected snapshot")
    checked = 0
    for (row_id, title, digest, game), entries in articles.items():
        pairs = printing_pairs(read_article(db, row_id, title, digest), game)
        for entry in entries:
            number = entry["match"]["number"]
            if entry.get("printingNumber", number) != number or (number, entry["names"]["ko"]) not in pairs:
                raise ValueError(f"Number and Korean name do not match in the same card entry: {number}")
            checked += 1
    return checked


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path, help="Existing namu-md.sqlite archive file")
    parser.add_argument("--seed", type=Path, default=DEFAULT_SEED, help="Reviewed card index JSON")
    args = parser.parse_args()
    try:
        uri = args.database.resolve(strict=True).as_uri() + "?mode=ro&immutable=1"
        with closing(sqlite3.connect(uri, uri=True)) as db:
            result = verify(db, json.loads(args.seed.read_text(encoding="utf-8")))
    except (OSError, sqlite3.Error, ValueError, KeyError, zlib.error) as exc:
        parser.exit(1, f"Verification failed: {exc}\n")
    print(f"Verified {result} wiki card number/name pairs in the {DATE} snapshot.")


if __name__ == "__main__":
    main()
