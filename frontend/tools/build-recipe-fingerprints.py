"""Compile a local Japanese Neuron artwork mirror into numerical comparison features.

Obtain the manifest and one JP Neuron mirror following the upstream bulk-use instructions:
https://github.com/yugioh-artworks/artworks-index#2-if-you-need-access-to-all-artworks
Run with Pillow. No network calls, scans, or arbitrary manifest URL downloads are performed.
"""

import argparse
import json
import struct
from pathlib import Path
from urllib.parse import urlsplit

from PIL import Image


HOST = "artworks-jp-n.ygoresources.com"


def build(manifest, mirror, output):
    cards = json.loads(manifest.read_text(encoding="utf-8"))["cards"]
    if (mirror / "CNAME").read_text(encoding="utf-8").strip() != HOST:
        raise ValueError("Expected the Japanese Neuron artwork mirror")
    root = mirror.resolve()
    records = bytearray()
    count = 0
    for cid, artworks in sorted(cards.items(), key=lambda item: int(item[0])):
        for artwork, item in sorted(artworks.items(), key=lambda pair: int(pair[0])):
            editions = item.get("idx", {}).get("ja", [])
            matches = [urlsplit(edition["path"]) for edition in editions
                       if urlsplit(edition["path"]).hostname == HOST]
            if not matches:
                continue
            path = (root / matches[0].path.lstrip("/")).resolve()
            if not path.is_relative_to(root) or path.suffix.lower() != ".png":
                raise ValueError("Unexpected artwork path")
            with Image.open(path) as original:
                image = original.convert("RGB")
                width, height = image.size
                box = (.105 * width, .185 * height, .895 * width, .72 * height)
                rgb = image.resize((6, 6), Image.Resampling.BOX, box).tobytes()
            packed = bytes((a & 240) | (b >> 4) for a, b in zip(rgb[::2], rgb[1::2]))
            records.extend(struct.pack("<IB", int(cid), int(artwork)))
            records.extend(packed)
            count += 1
    if not count:
        raise ValueError("No indexed artwork in this mirror")
    output.write_bytes(b"YNR1" + struct.pack("<I", count) + records)
    print(f"{count} artworks, {output.stat().st_size} bytes")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("mirror", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    build(args.manifest, args.mirror, args.output)
