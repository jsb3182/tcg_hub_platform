"""Build Korean card mechanics and pack metadata from verified articles; never emit article prose."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
import time
import unicodedata
from urllib.parse import urlencode

from bs4 import BeautifulSoup
from build_namuwiki_yugioh import articles
from tcg_worker.catalog_sources.card_names import ygo_name_archive
from verify_namuwiki_yugioh import AGENT, ATTRIBUTES, DATASET, DEFAULT_SEED, REVISION, fetch, publisher, publisher_rules


# Each pair recognizes the same mechanic in the monster's own card text and in
# independently identified official rules. The generated descriptions summarize a
# mechanic, not the complete cost, condition or effect of a complex card.
MECHANICS = [
    (r"상대필드에만몬스터가존재.{0,12}이카드(?:는|를)패에서특수소환",
     "상대만 몬스터를 조종할 때 이 카드를 패에서 특수 소환할 수 있다."),
    (r"상대메인페이즈.{0,12}이카드를패에서묘지로보내고.{0,14}상대필드의효과몬스터1장.{0,70}턴종료시까지.{0,12}효과를무효",
     "상대 메인 페이즈에 이 카드를 패에서 묘지로 보내 상대 필드의 효과 몬스터 한 장의 효과를 턴 종료 시까지 막을 수 있다."),
    (r"(?:카드|효과)의?발동을무효로하고파괴한다|그발동을무효로하고파괴한다",
     "효과에 발동 무효와 파괴 처리가 있다."),
    (r"(?:그|상대몬스터의|상대의)공격을무효로(?:한다|할수있다)",
     "공격을 무효로 하는 처리가 있다."),
    (r"1장을?드로우(?:한다|할수있다)", "한 장을 드로우하는 처리가 있다."),
    (r"이카드는상대(?:플레이어)?에게직접공격할수있다", "이 카드는 상대에게 직접 공격할 수 있다."),
    (r"이카드를묘지에서특수소환(?:한다|할수있다)", "이 카드 자신을 묘지에서 특수 소환하는 처리가 있다."),
    (r"이카드를패로되돌(?:린다|릴수있다)", "이 카드 자신을 패로 되돌리는 처리가 있다."),
]


def clean(text):
    return " ".join(unicodedata.normalize("NFKC", text).split())


def source_check(row, article):
    if (article["title"] != row["title"] or
            hashlib.sha256(article["text"].encode()).hexdigest() != row["articleSha256"]):
        raise ValueError("Article title or digest disagrees with the reviewed snapshot")


def ygo_metadata(row, article, printed, reference, api, products):
    source_check(row, article)
    card_name, official, _ = printed
    if card_name != row["names"]["ko"] or api.get("id") != int(row["match"]["passcode"]):
        raise ValueError("Publisher / catalog identity mismatch")
    stats = row["facts"]
    key = "rank" if "rank" in stats else "level"
    if not all(official.get(name)==stats.get(name) for name in (key,"atk","def")):
        raise ValueError("Publisher statistics differ")
    if ATTRIBUTES.get(official.get("attribute")) != stats.get("attribute"):
        raise ValueError("Publisher attribute differs")
    expected = " ".join(str(official[k]) for k in (key,"attribute","race","atk","def"))
    header = ("랭크" if key=="rank" else "레벨")+" 속성 종족 공격력 수비력"
    lines = [" ".join(line.split()) for line in article["text"].splitlines() if line.strip()]
    mechanics, kinds = set(), set()
    matched = False
    for i, line in enumerate(lines):
        if line != "한글판 명칭 "+card_name:
            continue
        for j in range(i+1,min(i+12,len(lines)-1)):
            if lines[j].startswith("한글판 명칭 "):
                break
            if lines[j]!=header or lines[j+1]!=expected or "영어판 명칭 "+api["name"] not in lines[i+1:j]:
                continue
            matched = True
            printed_type = lines[j-1]
            for english, korean in [("Synchro","싱크로"),("Xyz","엑시즈"),("Fusion","융합"),
                                    ("Tuner","튜너"),("Ritual","의식"),("Pendulum","펜듈럼")]:
                if english in api["type"] and korean in printed_type:
                    kinds.add(korean)
            if api["type"]=="Normal Monster" and printed_type=="일반 몬스터":
                kinds.add("일반 몬스터")
            # Start directly after the matching stats row. Accept only the first
            # rule line and explicitly numbered continuations, never the commentary.
            candidates = []
            for k, value in enumerate(lines[j+2:j+6]):
                if k and not re.match(r"^[①-⑳]",value):
                    break
                if not k and (len(value)>1500 or value.startswith(("한글판 명칭 ","일어판 명칭 ","영어판 명칭 "))):
                    break
                candidates.append(value)
            wiki_rules = "".join(candidates).replace(" ","")
            official_rules = reference.replace(" ","").replace("\n","")
            for pattern, label in MECHANICS:
                if re.search(pattern,wiki_rules) and re.search(pattern,official_rules):
                    mechanics.add(label)
            break
    if not matched:
        raise ValueError("Expected verified stats block is absent")
    details = {"traits": [official["attribute"]+" 속성",official["race"],*sorted(kinds)]}
    if mechanics:
        details["rulings"] = sorted(mechanics)
    number = row.get("printingNumber")
    for line in lines if number else ():
        match = re.fullmatch(r"(.{2,96}?)\s+"+re.escape(number)+r"(?:\s+.*)?",line)
        if not match:
            continue
        name = clean(match[1])
        if len(name) >= 2 and any(clean(p)==name or clean(p).startswith(name+" ") for p in products):
            details["packs"] = [f"{name} ({number})"]
            break
    extra = {"details":details}
    if mechanics:
        extra["textKo"] = " ".join(sorted(mechanics))
    elif "일반 몬스터" in kinds:
        extra["textKo"] = "자체 몬스터 효과가 없는 일반 몬스터다."
    return extra


def pokemon_metadata(row, article, printing):
    source_check(row,article)
    number, name = row["printingNumber"],row["names"]["ko"]
    card_key = "catalog:POKEMON:"+printing["external_id"]
    if (card_key!=row["match"]["catalogKey"] or printing["number"]!=row["match"]["number"]
            or printing["name"]!=name or row["verificationUrl"]!=printing["source_url"]
            or row["title"] not in printing["pack_name"]):
        raise ValueError("Korean Pokemon printing mismatch")
    specs = printing["specs"]
    base, total = number.split("/")
    if base!=printing["number"] or not str(specs.get("set_total","")).isdigit() or int(total)!=int(specs["set_total"]):
        raise ValueError("Korean pack numbering mismatch")
    prefix = clean(number+" "+name)+" "
    lines = [clean(line) for line in article["text"].splitlines()]
    if "컬렉션 넘버 카드명 종류 레어도" not in lines:
        raise ValueError("Missing collection table")
    matches = [line[len(prefix):] for line in lines if line.startswith(prefix)]
    if len(matches)!=1:
        raise ValueError("Ambiguous printed row")
    details = {"packs":[f"{printing['pack_name']} ({number})"]}
    tail = matches[0].split()
    traits = []
    if len(tail)>1 and tail[-1]==printing.get("rarity"):
        traits.append("레어도 "+tail[-1])
    category = " ".join(tail[:-1])
    stage = specs.get("stage")
    if (specs.get("card_type")=="Pokémon" and stage and category in (stage+" 포켓몬", stage+" 포켓몬 EX")) or category==specs.get("card_type"):
        traits.insert(0,category)
    if traits:
        details["traits"] = traits
    return {"details":details}


def read_viewer(titles):
    # DuckDB filter row_idx is a viewer locator. It is not a /rows offset.
    unique = list(dict.fromkeys(titles))
    for start in range(0,len(unique),5):
        where = " OR ".join("\"title\"='"+v.replace("'","''")+"'" for v in unique[start:start+5])
        u = "https://datasets-server.huggingface.co/filter?"+urlencode(
            {"dataset":DATASET, "config":"default", "split":"train", "where":where, "length":100})
        with fetch(u) as response:
            if response.headers.get("X-Revision")!=REVISION:
                raise ValueError("Snapshot revision changed")
            body=json.load(response)
        if body["num_rows_total"]!=len(body["rows"]):
            raise ValueError("Incomplete snapshot query")
        for entry in body["rows"]:
            if not entry["truncated_cells"]:
                yield entry["row"]


def official_details(row):
    with fetch(row["verificationUrl"]) as response:
        raw = response.read(1_500_001)
    if len(raw)>1_500_000:
        raise ValueError("Publisher page too large")
    doc = BeautifulSoup(raw,"html.parser")
    number = row.get("printingNumber")
    products = set()
    for code in doc.select("#update_list .card_number") if number else ():
        if code.get_text(strip=True)==number:
            labels=[s for s in code.parent.stripped_strings if s!=number]
            if len(labels)==1:
                products.add(labels[0])
    return publisher(raw),products


def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--seed",type=Path,default=DEFAULT_SEED)
    cli.add_argument("--out",type=Path,required=True)
    cli.add_argument("--dump",type=Path,nargs="+",help="Local ordered snapshot shards; otherwise use the pinned public viewer")
    cli.add_argument("--yaml-yugi",type=Path,required=True)
    cli.add_argument("--ygopro",type=Path,nargs="+",required=True)
    cli.add_argument("--pokemon",type=Path,required=True,help="Korean normalized catalog NDJSON")
    args=cli.parse_args()
    if args.out.exists():
        cli.error("Select a new output file")
    seed=json.loads(args.seed.read_text("utf8"))
    pending=defaultdict(list)
    for row in seed:
        pending[row["title"],row["articleSha256"]].append(row)
    selected={row["match"]["cid"] for row in seed if row["game"]=="YUGIOH"}
    api={}
    for page in args.ygopro:
        for record in json.loads(page.read_text("utf8"))["data"]:
            for match in record.get("misc_info",[]):
                if match.get("konami_id") in selected:
                    api[match["konami_id"],record["id"]]=record
    names=ygo_name_archive(args.yaml_yugi)
    keys={r["match"]["catalogKey"] for r in seed if r["game"]=="POKEMON"}
    with args.pokemon.open(encoding="utf8") as stream:
        poke={key:r for line in stream if (r:=json.loads(line)) and (key:="catalog:POKEMON:"+r["external_id"]) in keys}
    rules=publisher_rules()
    inputs=articles(args.dump) if args.dump else read_viewer([r["title"] for r in seed])
    for article in inputs:
        key=(article["title"],hashlib.sha256(article["text"].encode()).hexdigest())
        for row in pending.pop(key,[]):
            if row["game"]=="POKEMON":
                extra=pokemon_metadata(row,article,poke[row["match"]["catalogKey"]])
            elif row["game"]=="YUGIOH":
                cid=row["match"]["cid"]
                if not rules.can_fetch(AGENT,row["verificationUrl"]):
                    raise ValueError("Publisher verification denied")
                time.sleep(max(1,rules.crawl_delay(AGENT) or 0))
                official,products=official_details(row)
                extra=ygo_metadata(row,article,official,names[str(cid)]["texts"].get("ko",""),
                                   api[cid,int(row["match"]["passcode"])],products)
            else:
                continue
            row.pop("textKo",None)
            row.update(extra)
    if pending:
        raise ValueError("An original article digest could not be reproduced")
    with args.out.open("x",encoding="utf8") as f:
        json.dump(seed,f,ensure_ascii=False,indent=2)
        f.write("\n")


if __name__=="__main__":
    main()
