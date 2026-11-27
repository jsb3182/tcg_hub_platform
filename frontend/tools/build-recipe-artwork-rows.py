"""Generate the INSERT values for a new Neuron artwork migration, from upstream paths only."""
import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlsplit


def rows(manifest):
    cards = json.loads(manifest.read_text(encoding="utf8"))["cards"]
    for cid, pictures in sorted(cards.items(), key=lambda pair: int(pair[0])):
        for artwork, editions in sorted(pictures.items(), key=lambda pair: int(pair[0])):
            for entry in editions.get("idx", {}).get("ja", []):
                path = urlsplit(entry["path"])
                if path.hostname != "artworks-jp-n.ygoresources.com":
                    continue
                if not (re.fullmatch(r"[1-9][0-9]{0,8}", cid)
                        and re.fullmatch(r"[1-9][0-9]{0,3}", artwork)
                        and re.fullmatch(r"/[0-9]+/[0-9]+/[0-9]+_[0-9]+\.png", path.path)
                        and not path.query and not path.fragment):
                    raise ValueError("Unsupported official artwork mapping")
                yield f"('{cid}',{artwork},'{path.path}')"
                break


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    entries = list(rows(args.manifest))
    if not entries:
        raise ValueError("No Japanese Neuron entries")
    with args.output.open("x", encoding="utf8", newline="\n") as out:
        for start in range(0,len(entries),1000):
            out.write("INSERT INTO neuron_artwork(cid,artwork,image_path) VALUES\n")
            out.write(",\n".join(entries[start:start+1000])+";\n")
    print(f"{len(entries)} explicit publisher paths")
