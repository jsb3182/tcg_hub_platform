"""PC-only factual reference builder for a locally acquired, versioned wiki snapshot."""
import argparse
from collections import Counter, defaultdict
from datetime import date
import gzip
import hashlib
import json
from pathlib import Path
import re
import sys
import time
from urllib.parse import quote, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tcg_worker.catalog_sources.card_names import ygo_name_archive
from verify_namuwiki_yugioh import AGENT, KONAMI, confirm, fetch, publisher, publisher_rules


def articles(paths):
    """Preserve combined input order (the published parquet shard order is significant)."""
    for path in paths:
        if path.suffix == ".parquet":
            import pyarrow.parquet as pq
            for batch in pq.ParquetFile(path).iter_batches(columns=["title", "text"], batch_size=32):
                yield from batch.to_pylist()
        elif path.name.endswith((".jsonl", ".jsonl.gz", ".ndjson", ".ndjson.gz")):
            opener = gzip.open if path.suffix == ".gz" else open
            with opener(path, "rt", encoding="utf-8") as stream:
                for line in stream:
                    yield json.loads(line)
        else:
            raise ValueError(f"Unsupported snapshot format: {path}")


def identities(yaml_archive, api_pages):
    names = ygo_name_archive(yaml_archive)
    by_name = defaultdict(dict)
    for page in api_pages:
        for card in json.loads(page.read_text("utf-8"))["data"]:
            # Keep only matching facts in memory. Full text, images and prices are unnecessary.
            cids = {i["konami_id"] for i in card.get("misc_info", []) if i.get("konami_id")}
            if len(cids) != 1:
                continue
            cid = cids.pop()
            edition = names.get(str(cid), {})
            labels = edition.get("names", {})
            ko = labels.get("ko")
            if not ko or labels.get("en") != card["name"]:
                continue
            facts = {k: card[k] for k in ("level", "atk", "def", "race", "attribute") if k in card}
            if len(facts) != 5 or not all(isinstance(facts[k], int) for k in ("level", "atk", "def")):
                continue
            by_name[ko][cid, card["id"]] = (
                {"id": card["id"], "name": card["name"], "misc_info": [{"konami_id": cid}], **facts},
                labels, "Xyz" in card["type"], set(edition.get("printings", {}).get("ko", []))
            )
    return {name: next(iter(candidates.values())) for name, candidates in by_name.items() if len(candidates) == 1}


def build(cards, read_articles, snapshot_date, snapshot_url, get_official, limit=None):
    # Real historical rows include distinct pages with identical titles.
    counts = Counter(a["title"] for a in read_articles() if a["title"] in cards)
    requests = 0
    for index, article in enumerate(read_articles()):
        title = article["title"]
        if counts.get(title) != 1:
            continue
        api, labels, ranked, known_codes = cards[title]
        body = article["text"]
        lines = {" ".join(line.split()) for line in body.splitlines()}
        if "한글판 명칭 " + title not in lines or "영어판 명칭 " + api["name"] not in lines:
            continue
        cid = api["misc_info"][0]["konami_id"]
        link = f"{KONAMI}/yugiohdb/card_search.action?ope=2&cid={cid}&request_locale=ko"
        if limit is not None and requests >= limit:
            return
        official = get_official(link)
        requests += 1
        names = {"ko": title, "en": api["name"]}
        ja = labels.get("ja")
        facts = {k: api[k] for k in ("level", "race", "attribute", "atk", "def")}
        if ranked:
            facts["rank"] = facts.pop("level")
        candidate = {
            "game": "YUGIOH", "title": title, "url": "https://namu.wiki/w/" + quote(title, safe=""),
            "snapshotDate": snapshot_date, "snapshotUrl": snapshot_url, "snapshotRow": index,
            "articleSha256": hashlib.sha256(body.encode()).hexdigest(), "language": "ko", "names": names,
            "match": {"cid": cid, "passcode": str(api["id"]).zfill(8)}, "facts": facts, "verificationUrl": link
        }
        if not confirm(candidate, article, api, official, snapshot_url):
            continue
        if ja:
            japanese = {**candidate, "names": {**names, "ja": ja}}
            if confirm(japanese, article, api, official, snapshot_url):
                candidate = japanese
        tokens = set(re.findall(r"(?<![A-Za-z0-9-])[A-Z0-9]{2,8}-(?:KR|K)?[0-9]{2,4}(?![A-Za-z0-9-])", body))
        codes = sorted(known_codes & official[2] & tokens)
        if codes:
            candidate["printingNumber"] = codes[0]
        yield candidate


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--dump", nargs="+", type=Path, required=True, help="All local shards, in source order")
    cli.add_argument("--snapshot-date", type=date.fromisoformat, required=True)
    cli.add_argument("--snapshot-url", required=True, help="Publisher or distributor's pinned snapshot revision")
    cli.add_argument("--yaml-yugi", type=Path, required=True, help="Versioned YAML Yugi archive")
    cli.add_argument("--ygopro", type=Path, nargs="+", required=True, help="Public YGOPRODeck cardinfo JSON pages with misc=yes")
    cli.add_argument("--out", type=Path, required=True, help="New output file containing verified identities only")
    cli.add_argument("--limit", type=int, help="Maximum number of official card pages to request")
    args = cli.parse_args()
    if args.out.exists() or (args.limit is not None and args.limit < 1):
        cli.error("Choose a new output file and a positive request limit")
    if urlsplit(args.snapshot_url).scheme != "https" or not urlsplit(args.snapshot_url).netloc:
        cli.error("The snapshot requires an identifiable HTTPS source")
    rules = publisher_rules()

    def get_official(link):
        if not rules.can_fetch(AGENT, link):
            raise ValueError("Publisher disallows this verification request")
        time.sleep(max(1, rules.crawl_delay(AGENT) or 0))
        with fetch(link) as response:
            return publisher(response)

    cards = identities(args.yaml_yugi, args.ygopro)
    rows = list(build(cards, lambda: articles(args.dump), args.snapshot_date.isoformat(), args.snapshot_url,
                      get_official, args.limit))
    with args.out.open("x", encoding="utf-8") as output:
        json.dump(rows, output, indent=2, ensure_ascii=False)
        output.write("\n")
    print(f"Verified {len(rows)} card identities.")


if __name__ == "__main__":
    main()
