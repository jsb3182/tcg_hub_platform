"""Join confirmed One Piece regional cards by collector number and product, never by translated name."""
import hashlib
import json
import logging
import os
import re
import time
from collections import defaultdict
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit

from bs4 import BeautifulSoup
from protego import Protego

from .bulk import document, revision

REPO = "hotavocado/koala-kollect-data"
KOREA = "https://www.onepiece-cardgame.kr"
CARD_LIST = KOREA + "/cardlist.do"
OPTCG = "https://optcgapi.com/api/"
COLLECTOR = re.compile(r"((?:OP|ST|EB|PRB)[0-9]{2}-[0-9]{3}|P-[0-9]{3})(?:_[a-z0-9]+)?", re.I)
PACK = re.compile(r"(OP|ST|EB|PRB)K?-?([0-9]{2})", re.I)
SINGLE_PRODUCT = re.compile(r"(?:OP|ST|EB|PRB)-[0-9]{2}")
COLOR = {"적색": "red", "녹색": "green", "청색": "blue", "자색": "purple", "흑색": "black", "황색": "yellow"}
KIND = {"리더": "leader", "캐릭터": "character", "이벤트": "event", "스테이지": "stage", "두웅!!": "don"}


def code(value):
    match = COLLECTOR.fullmatch((value or "").strip())
    return match[1].upper() if match else None


def pack_code(label):
    match = PACK.search(label or "")
    return match[1].upper() + "-" + match[2] if match else "PROMO"


def edition(name, text, image, source):
    return {k: v for k, v in {"name": name, "text": text, "image": image, "source": source}.items() if v}


class Index:
    def __init__(self):
        self.editions = defaultdict(dict)
        self.printings = defaultdict(dict)
        self.products = defaultdict(dict)
        self.product_labels = defaultdict(set)
        self.rules = defaultdict(dict)
        self.korean_incomplete = False

    def add(self, number, lang, value, priority, product=None, product_name=None, *, observed_code=None, **facts):
        if not value.get("name"):
            return
        value = {**value, "editionProduct": product}
        if value.get("image"):
            value = {**value, "imageSource": value.get("imageSource") or value["source"]}
            # PROMO groups several products without a known set code.
            if product and product != "PROMO":
                value["imageProduct"] = product
        # Prefer the base art, then official edition metadata, then a stable source URL.
        rank = (priority, value.get("image", ""), value["name"])
        for group in [self.editions[number]] + ([self.printings[product, number]] if product else []):
            if lang not in group or rank < group[lang][0]:
                group[lang] = rank, value
        if product_name:
            self.products[product][lang] = product_name
            if product == observed_code and SINGLE_PRODUCT.fullmatch(product or ""):
                self.product_labels[product].add(product_name)
                # The English publisher's card index wraps the original title in a product type and SKU.
                if lang == "en" and value.get("source", "").startswith("https://en.onepiece-cardgame.com/cardlist/"):
                    label = re.fullmatch(r"(?:BOOSTER PACK|EXTRA BOOSTER|PREMIUM BOOSTER|STARTER DECK)\s+-\s*(.+?)\s*-\s*\["
                                         + re.escape(product) + r"\]", product_name, flags=re.I)
                    if label:
                        self.product_labels[product].add(label[1])
        for key, field in facts.items():
            if field not in (None, [], ""):
                self.rules[number].setdefault(key, field)

    def records(self):
        for (product, number), printings in sorted(self.printings.items()):
            translations = {lang: value for lang, (_, value) in self.editions[number].items()}
            translations.update({lang: value for lang, (_, value) in printings.items()})
            lang = next(lang for lang in ("ko", "en", "ja") if lang in translations)
            card = translations[lang]
            fields = {}
            for key, plural in (("name", "names"), ("text", "texts"), ("image", "images"), ("source", "sources"),
                                ("imageProduct", "imageProducts"), ("imageSource", "imageSources")):
                fields[plural] = {language: value[key] for language, value in translations.items() if value.get(key)}
            korean = translations.get("ko", {})
            if korean.get("source", "").startswith(CARD_LIST) and korean.get("editionProduct") not in (None,"PROMO"):
                fields["nameBasis"] = {"ko": "PRINTED_NAME" if korean["editionProduct"] == product else "RELATED_PRINTING"}
            if korean.get("regionalFacts"):
                fields["regionalFacts"] = {"ko": korean["regionalFacts"]}
            product_names = self.products[product]
            name = next((product_names[k] for k in ("ko", "en", "ja") if k in product_names), product)
            info = self.rules[number]
            yield {"external_id": f"{product}:{number}", "pack_code": product, "pack_name": name,
                   "pack_labels": sorted(self.product_labels[product]),
                   "korean_incomplete": self.korean_incomplete,
                   "number": number, "name": card["name"], "original_name": translations.get("en", card)["name"],
                   "effect": card.get("text"), "rarity": info.get("rarity"), "release_date": None,
                   "specs": {"language": lang, "productCode": product, **fields, **info}, "source_url": card["source"]}


def koala(index, http):
    sha = revision(http, REPO, "data")
    raw = f"https://raw.githubusercontent.com/{REPO}/{sha}/"
    manifest = document(http.get(raw + "manifest.json", family="onepiece-manifest"))["files"]

    def lines(key):
        path = f"data/{key}.jsonl"
        signature = manifest[path]["sha256"]
        file = http.get(raw + path, ttl=365*86400, size=20_000_000, family="onepiece/" + path)
        with file.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != signature:
                raise ValueError("Koala Kollect dataset checksum mismatch")
            stream.seek(0)
            for line in stream:
                yield json.loads(line)

    cards = {r["key"]: code(r.get("number")) for r in lines("cards")}
    for site, lang in (("jp", "ja"), ("en", "en")):
        publisher_index = "https://www.onepiece-cardgame.com/cardlist/" if lang == "ja" else "https://en.onepiece-cardgame.com/cardlist/"
        products = {r["key"]: r for r in lines("products/" + site)}
        packs = defaultdict(list)
        for link in lines("printing_products/" + site):
            packs[link["printing_key"]].append(products[link["product_key"]])
        observations = {}
        for obs in lines("card_observations/" + site):
            key = obs["card_key"]
            if key not in observations or observations[key]["first_seen_at"] < obs["first_seen_at"]:
                observations[key] = obs
        for pr in lines("printings/" + site):
            obs = observations.get(pr["card_key"])
            number = cards.get(pr["card_key"])
            if not number or not obs:
                continue
            image = pr.get("image_url")
            if image and urlsplit(image).hostname not in ("en.onepiece-cardgame.com", "www.onepiece-cardgame.com"):
                image = None
            for product in packs[pr["key"]] or [None]:
                source = (product or {}).get("product_url") or "https://github.com/" + REPO
                text = "\n".join(str(obs[k]) for k in ("effect", "trigger") if obs.get(k))
                value = edition(obs["name"], text, image, source)
                if image:
                    value["imageSource"] = (product or {}).get("product_url") or raw + f"data/printings/{site}.jsonl"
                index.add(number, lang, value,
                          0 if pr.get("variant") == "base" else 2,
                          pack_code(product["code"]) if product and product.get("code") else None,
                          product.get("name") if product and product.get("code") else None,
                          observed_code=product.get("code") if product and source.startswith(publisher_index) else None,
                          type=obs.get("category"), colors=obs.get("colors"), cost=obs.get("cost"),
                          power=obs.get("power"), rarity=pr.get("rarity"))


def optcg(index, http):
    for endpoint in ("allSetCards", "allSTCards", "allDonCards"):
        rows = document(http.get(OPTCG + endpoint + "/", ttl=86400, size=12_000_000, delay=1))
        if not isinstance(rows, list) or not rows:
            raise ValueError(f"Empty OPTCG bulk response: {endpoint}")
        for row in rows:
            ident = row.get("card_image_id") or ""
            don = endpoint == "allDonCards"
            number = "DON:" + ident if don and ident else code(row.get("card_set_id"))
            if not number:
                continue
            image = row.get("card_image")
            if image and urlsplit(image).hostname not in ("optcgapi.com", "www.optcgapi.com"):
                image = None
            link = OPTCG + endpoint + "/" if don else OPTCG + ("decks/card/" if endpoint == "allSTCards" else "sets/card/") + number + "/"
            index.add(number, "en", edition(row["card_name"], row.get("card_text"), image, link),
                      1 if ident.upper() == number else 3, pack_code(row.get("set_id")), row.get("set_name"),
                      observed_code=row.get("set_id"),
                      type="don" if don else str(row.get("card_type") or "").lower(),
                      colors=[x.lower().strip() for x in re.split(r"[,/]", row.get("card_color") or "") if x.strip()],
                      life=row.get("life"), cost=row.get("card_cost"), power=row.get("card_power"), rarity=row.get("rarity"))


def korean_facts(values, product, source):
    facts = {}
    attribute = values.get("cardAttr", "").strip()
    if attribute and attribute != "-":
        facts["attribute"] = attribute
    traits = [v.strip() for v in values.get("cardPoint", "").split("/") if v.strip() not in ("", "-")]
    if traits:
        facts["traits"] = list(dict.fromkeys(traits))
    # The official detail popup displays its single "life" field as 라이프 only
    # for leaders; the other card types use the 코스트 label.
    kind = KIND.get(values.get("cardType"))
    numbers = {"power": "power", "counter": "cardCounter"}
    if kind:
        numbers["life" if kind == "leader" else "cost"] = "life"
    for key, source_key in numbers.items():
        raw = values.get(source_key, "")
        if re.fullmatch(r"[0-9]{1,6}", raw):
            facts[key] = int(raw)
    if facts:
        facts["sourceUrl"] = source
        if product and product != "PROMO":
            facts["productCode"] = product
    return facts


def korean_page(index, body, source, series):
    soup = BeautifulSoup(body, "html.parser")
    cards = soup.select(".card_sch_list button.item")
    for elem in cards:
        # The publisher omits closing </p> tags. Read a field's direct text only.
        values = {p["class"][0]: " ".join(str(s).strip() for s in p.find_all(string=True, recursive=False)).strip()
                  for p in elem.select("p[class]")}
        printing = values.get("cardNumber", "")
        number = code(printing)
        if not number:
            continue
        image = elem.select_one("img.image[src]")
        url = urljoin(KOREA, image["src"]) if image else None
        if url and (urlsplit(url).netloc != urlsplit(KOREA).netloc or urlsplit(url).path != "/fileDownload"):
            url = None
        pack = values.get("cardGet") or series
        effect = "\n".join(values[k] for k in ("cardText", "cardTrigger") if values.get(k) not in (None, "", "-"))
        product = pack_code(pack)
        bracket = re.match(r"^\[(OP|ST|EB|PRB)K-([0-9]{2})\]", pack or "")
        value = edition(values.get("cardName"), effect, url, source)
        value["regionalFacts"] = korean_facts(values, product, source)
        index.add(number, "ko", value,
                  0 if number == printing.upper() else 2, product, pack,
                  observed_code="-".join(bracket.groups()) if bracket else None,
                  type=KIND.get(values.get("cardType")), colors=[COLOR[c.strip()] for c in values.get("cardColor", "").split(",") if c.strip() in COLOR])
    next_link = soup.select_one("a.pagi_next[href]")
    if not next_link:
        return None
    page = parse_qs(urlsplit(next_link["href"]).query).get("page", [""])[0]
    if not page.isdecimal() or not cards:
        raise ValueError("Invalid Korean One Piece catalog continuation")
    return int(page)


def korean(index, http):
    robot = http.get(KOREA + "/robots.txt", ttl=86400).read_text("utf-8", errors="replace")
    policy = Protego.parse(robot)
    if not policy.can_fetch(CARD_LIST, "TCGHub-Catalog"):
        raise ValueError("The Korean One Piece catalog is not open for this worker")
    body = http.get(CARD_LIST, ttl=86400).read_bytes()
    home = BeautifulSoup(body, "html.parser")
    korean_page(index,body,CARD_LIST,"")
    series = list(dict.fromkeys(opt["value"] for opt in home.select("select option[value]")
                                if PACK.search(opt["value"]) or "프로모션" in opt["value"]))
    if not series:
        raise ValueError("No Korean One Piece products found")
    # Always rebuild from verified local pages first. Spread historical downloads over
    # multiple catalog runs so a slow page does not hold up every language on the phone.
    checkpoint = http.root / ".onepiece-korea-position"
    start = checkpoint.read_text("utf-8") if checkpoint.is_file() else ""
    if start in series:
        pos = series.index(start)+1
        ordered = series[pos:]+series[:pos]
    else:
        ordered = series
    def target(name,page):
        url = CARD_LIST + "?" + urlencode({"series":name,"page":page,"size":20})
        if not policy.can_fetch(url,"TCGHub-Catalog"):
            raise ValueError("Korean One Piece product is not open for this worker")
        return url
    def parse(name,page,url,body):
        following=korean_page(index,body,url,name)
        if following is not None and (following!=page+1 or following>150):
            raise ValueError("Unexpected Korean One Piece catalog page")
        return following
    missing, refresh = [], []
    for name in ordered:
        page=0
        ttl=(1 if name in series[:2] or "프로모션" in name else 7)*86400
        while page is not None:
            url=target(name,page)
            path=http.root / hashlib.sha256(url.encode()+b"\0").hexdigest()
            if not path.is_file():
                missing.append((name,page,url,ttl))
                break
            if time.time()-path.stat().st_mtime>=ttl:
                refresh.append((name,page,url,ttl))
            page=parse(name,page,url,path.read_bytes())
    queue=missing+refresh
    budget=24
    failed_products=set()
    consecutive_failures=0
    while queue and budget:
        name,page,url,ttl=queue.pop(0)
        if name in failed_products:
            continue
        temp=checkpoint.with_suffix(".tmp")
        temp.write_text(name,"utf-8")
        os.replace(temp,checkpoint)
        budget-=1
        try:
            body=http.get(url,ttl=ttl,delay=1).read_bytes()
        except (OSError,URLError) as exc:
            if isinstance(exc,HTTPError) and (exc.code<500 or exc.code==503):
                raise   # Preserve authentication, rate limits and Retry-After for the scheduler.
            logging.getLogger(__name__).warning("Korean One Piece history deferred at %s page %s (%s)",pack_code(name),page,type(exc).__name__)
            failed_products.add(name)
            consecutive_failures+=1
            if consecutive_failures>=3:
                break
            continue
        consecutive_failures=0
        following=parse(name,page,url,body)
        if following is not None:
            nxt=target(name,following)
            if not (http.root/hashlib.sha256(nxt.encode()+b"\0").hexdigest()).exists():
                queue.append((name,following,nxt,ttl))
    index.korean_incomplete=bool(failed_products or queue)


def onepiece(http):
    index = Index()
    koala(index, http)
    optcg(index, http)
    korean(index, http)
    if not index.printings or not all(any(lang in group for group in index.editions.values()) for lang in ("ko","en","ja")):
        raise ValueError("One Piece catalog is missing a regional edition")
    yield from index.records()


def preserve_partial_korean(db, cards):
    # A history scan can stop at its request budget before re-reading an older print.
    # Keep the previous verified edition together with its source and artwork provenance.
    partial = [key for key, row in cards.items() if row.get("korean_incomplete")]
    if not partial:
        return
    rows = db.execute("""
        SELECT legacy_key,number,specs FROM card WHERE game_code='ONEPIECE' AND legacy_key=ANY(%s)
          AND nullif(specs->'names'->>'ko','') IS NOT NULL
        """,(partial,)).fetchall()
    for key, number, prior in rows:
        row = cards[key]
        current = row["specs"]
        product = current.get("productCode")
        if number != row["number"] or not product or product != prior.get("productCode"):
            continue
        source = (prior.get("sources") or {}).get("ko") or ""
        url = urlsplit(source)
        if (url.scheme,url.netloc,url.path) != ("https","www.onepiece-cardgame.kr","/cardlist.do"):
            continue
        old_exact = (prior.get("imageProducts") or {}).get("ko")==product or (prior.get("nameBasis") or {}).get("ko")=="PRINTED_NAME"
        if (current.get("names") or {}).get("ko") and not (old_exact and (current.get("nameBasis") or {}).get("ko")=="RELATED_PRINTING"):
            continue
        merged = {**current}
        for field in ("names","texts","sources","images","imageSources","imageProducts","nameBasis","regionalFacts"):
            languages = dict(current.get(field) or {})
            languages.pop("ko",None)
            if "ko" in (prior.get(field) or {}):
                languages["ko"] = prior[field]["ko"]
            if languages or field in current:
                merged[field] = languages
        row.update(specs={**merged,"language":"ko"},name=prior["names"]["ko"],
                   effect=(prior.get("texts") or {}).get("ko"),source_url=source)
