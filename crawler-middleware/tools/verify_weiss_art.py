"""Report Weiss EN image references from a pinned catalog ZIP and optional saved publisher HTML.

Run with PYTHONPATH=crawler-middleware. Reads supplied files only and does not fetch images.
"""
import argparse
from collections import Counter
import csv
import gzip
import json
from pathlib import Path
import re
import zipfile

from tcg_worker.catalog_sources import weiss_art


def verify(archive_path, inventory, details, output):
    pending = None
    if inventory:
        with gzip.open(inventory, "rt", encoding="utf-8-sig", newline="") as stream:
            pending = {row["number"] for row in csv.DictReader(stream)
                       if row["game"] == "WEISS" and row["eligibleURL"] == "0"}
    counts = Counter()
    checked = {}
    seen = set()
    with zipfile.ZipFile(archive_path) as archive:
        roots = {p.split("/", 1)[0] for p in archive.namelist()}
        if len(roots) != 1:
            raise ValueError("Expected one pinned catalog repository")
        match = re.fullmatch(r"WeissSchwarz-ENG-DB-([0-9a-f]{40})", roots.pop())
        if not match:
            raise ValueError("Expected commit SHA in archive root")
        sha = match[1]
        ambiguous = weiss_art.conflicting_prints(archive)
        for filename, cards in weiss_art.sets(archive):
            for card in cards:
                code = card["code"].strip()
                if code in seen:
                    continue
                seen.add(code)
                refs = weiss_art.metadata(card, sha, filename, ambiguous)
                art = refs.get("publisherArtwork", {}).get("en")
                if art:
                    counts[art["basis"]] += 1
                    if pending and code in pending:
                        counts["previouslyMissingWithReference"] += 1
                if code in details:
                    page = weiss_art.from_detail(card, details[code].read_bytes(), "local reproduction")
                    if not page or not art or art["basis"] != "PUBLISHER_CARD_DETAIL" or any(
                        page[key] != art[key] for key in ("imageUrl","htmlSha256")
                    ):
                        raise ValueError("Reviewed publisher reference does not match the supplied snapshot: " + code)
                    checked[code] = page["htmlSha256"]
                if output:
                    output.write(json.dumps({"catalogKey": "catalog:WEISS:en:" + code, **refs}, ensure_ascii=False) + "\n")
    if set(details) != checked.keys() or (pending is not None and not pending.issubset(seen)):
        raise ValueError("Input contains a printing outside the selected catalog revision")
    return {"revision": sha, "prints": len(seen), "previouslyMissing": len(pending) if pending is not None else None,
            "imageReferences": dict(counts), "reproducedOfficialPages": checked}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--inventory", type=Path, help="Optional existing V59 cards.csv.gz coverage report")
    parser.add_argument("--detail", action="append", default=[], nargs=2, metavar=("NUMBER", "SAVED_HTML"))
    parser.add_argument("--mapping", type=Path, help="Create a new metadata-only .jsonl.gz")
    args = parser.parse_args()
    detail_files = {number: Path(file) for number,file in args.detail}
    if args.mapping:
        with gzip.open(args.mapping, "xt", encoding="utf8") as target:
            report = verify(args.archive, args.inventory, detail_files, target)
    else:
        report = verify(args.archive, args.inventory, detail_files, None)
    print(json.dumps(report, indent=2))
