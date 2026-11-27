"""Reproduce the Korean product/date index from the maintainer's aggregate ZIP."""
import argparse
from datetime import date
import gzip
import hashlib
import json
from pathlib import Path
import zipfile


SNAPSHOT_SHA256 = "8313f46bef72150c99633f4dc70436bdb8ac70a3d6176a39d8134a49c35f3fea"
OBSERVED_ON = date(2026, 4, 7)


def build(archive):
    with archive.open("rb") as source:
        if hashlib.file_digest(source, "sha256").hexdigest() != SNAPSHOT_SHA256:
            raise ValueError("YGOJSON archive does not match the published SHA-256")
    with zipfile.ZipFile(archive) as source:
        with source.open("cards.json") as cards:
            ids = {row["id"]: row["externalIDs"]["dbID"] for row in json.load(cards)
                   if isinstance(row.get("externalIDs", {}).get("dbID"), int)}
        with source.open("sets.json") as products:
            sets = json.load(products)
    result = {}
    products = {}
    for item in sets:
        kr = item.get("locales", {}).get("kr", {})
        if kr.get("language") != "ko" or not kr.get("date"):
            continue
        released = date.fromisoformat(kr["date"])
        if released > OBSERVED_ON:
            continue
        for group in item["contents"]:
            if "kr" not in group.get("locales", ()) or "ocg" not in group.get("formats", ()):
                continue
            for card in group.get("cards", ()):
                cid = ids.get(card["card"])
                if not cid or not card.get("suffix"):
                    continue
                number = (kr.get("prefix") or "") + card["suffix"]
                if "-K" not in number:
                    continue
                key = str(cid), number
                product = item["id"]
                if key in result and result[key] != product:
                    # Conflicting product assignments cannot establish one release date.
                    result[key] = None
                    continue
                result[key] = product
                products[product] = kr["date"]
    unique_products = sorted({product for product in result.values() if product})
    positions = {product: i for i, product in enumerate(unique_products)}
    rows = {}
    for (cid, number), product in sorted(result.items()):
        if product:
            rows.setdefault(cid, {})[number] = positions[product]
    return {"products": [[uid, products[uid]] for uid in unique_products], "cards": rows}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    index = build(args.archive)
    output = json.dumps(index, separators=(",", ":"), sort_keys=True).encode("ascii")
    with args.output.open("wb") as stream, gzip.GzipFile(filename="", fileobj=stream, mode="wb", mtime=0) as target:
        target.write(output)
