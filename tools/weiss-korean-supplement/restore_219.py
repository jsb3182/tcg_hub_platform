"""Reconstruct the archived 2.0.19 base memory on a PC and verify its published SHA-256."""
import argparse
import gzip
from hashlib import sha256
import io
import json
from pathlib import Path
import zipfile

from tcg_worker.catalog_sources.weiss_art import sets
from tcg_worker.catalog_sources.weiss_korean import source_effect
from tcg_worker.weiss_readings import VERSION, memory_key


ZIP_SHA = "f1b341a6b3e3df359ca4c3bd55fc823c2510b60df66dfb7e04be851b8c81c720"
PAYLOAD_SHA = "31a8a3f0537c2d2e5caaa323f86fd4b7b60ee7b547dab1e73d9a3463c93bdb88"
RELEASE_SHA = "9e2aec465df74daf1f4bc1878bb9f38b76833bbfd89e71564a0646f24ca76590"
DELTA_SHA = "984aca31c8385e851f8d7085bf6cd19d97b9434debb42f553e75a9828e212c07"
MAX_PAYLOAD = 16 * 1024 * 1024


def recover_source_rows(archive, missing):
    # Four historical keys are handled by the current dictionary before model inference.
    # Resolve their English source in the operator-supplied pinned ZIP.
    recovered = {}
    with zipfile.ZipFile(archive) as source:
        for _, cards in sets(source):
            for card in cards:
                family = card["code"].strip().partition("/")[0]
                originals = [("name", family, card["name"].strip())]
                effect = source_effect(card["ability"]) or ""
                originals.extend(("rule", "", line.strip()) for line in effect.splitlines() if line.strip())
                for kind, group, text in originals:
                    key = memory_key(kind, text, group).hex()
                    if key in missing:
                        recovered[key] = [kind, group, text, None, key]
                if len(recovered) == len(missing):
                    return recovered
    raise ValueError("Could not identify all historical source keys in the pinned catalog")


def restore(archive, generated):
    with archive.open("rb") as stream:
        digest = sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    if digest.hexdigest() != ZIP_SHA:
        raise ValueError("This reconstruction requires the exact 2.0.19 English catalog ZIP")
    with gzip.open(generated, "rb") as stream:
        payload = stream.read(MAX_PAYLOAD + 1)
    if len(payload) > MAX_PAYLOAD:
        raise ValueError("Unexpected generated memory size")
    if sha256(payload).hexdigest() != PAYLOAD_SHA:
        lines = iter(payload.decode().splitlines())
        if json.loads(next(lines, "null")) != {"version": VERSION}:
            raise ValueError("Incompatible translation memory header")
        rows = {}
        for line in lines:
            row = json.loads(line)
            kind, group, original, _, key = row
            if key in rows or memory_key(kind, original, group).hex() != key:
                raise ValueError("Unexpected or duplicate translation unit")
            rows[key] = row
        delta = Path(__file__).with_name("memo-219-delta.jsonl").read_text(encoding="utf8")
        if sha256(delta.encode()).hexdigest() != DELTA_SHA:
            raise ValueError("Unexpected reconstruction delta SHA-256")
        changes = dict(map(json.loads, delta.splitlines()))
        missing = changes.keys() - rows.keys()
        if missing:
            rows.update(recover_source_rows(archive, missing))
        for key, value in changes.items():
            rows[key][3] = value
        header = json.dumps({"version": VERSION})
        lines = (json.dumps(row, ensure_ascii=False, separators=(",", ":"))
                 for row in sorted(rows.values(), key=lambda row: row[:3]))
        payload = (header + "\n" + "\n".join(lines) + "\n").encode()
        if sha256(payload).hexdigest() != PAYLOAD_SHA:
            raise ValueError("This inference run differs outside the verified reconstruction delta")
    compressed = io.BytesIO()
    # Original Python gzip header and final text-mode flush are part of the release digest.
    with gzip.GzipFile(filename="weiss-ko-219-final.jsonl.gz.tmp", fileobj=compressed,
                       mode="wb", compresslevel=9, mtime=1795876624) as zipped:
        with io.TextIOWrapper(zipped, encoding="utf8", newline="\n") as stream:
            stream.write(payload.decode())
    data = compressed.getvalue()
    if sha256(data).hexdigest() != RELEASE_SHA:
        raise ValueError("Content matched but this zlib produced different compressed bytes")
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("generated", type=Path)
    parser.add_argument("output", type=Path, help="new file; an existing file must already match")
    args = parser.parse_args()
    data = restore(args.archive, args.generated)
    try:
        target = args.output.open("xb")
    except FileExistsError:
        if args.output.stat().st_size != len(data) or args.output.read_bytes() != data:
            parser.error("The output exists and differs from the release")
    else:
        try:
            with target:
                target.write(data)
        except OSError:
            args.output.unlink(missing_ok=True)
            raise
    print(RELEASE_SHA)


if __name__ == "__main__":
    main()
