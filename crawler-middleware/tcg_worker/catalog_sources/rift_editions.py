"""Match RiftHunt printings to Riot's English and Korean public card galleries."""
import json
import logging
import re
from html.parser import HTMLParser
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser


ORIGIN = "https://playriftbound.com"
GALLERIES = {locale: f"{ORIGIN}/{locale}/card-gallery/" for locale in ("en-us", "ko-kr")}
HANGUL = re.compile(r"[가-힣]")
ART = re.compile(r"/sanity/images/dsfx7636/game_data_live/([0-9a-f]{40})-[1-9][0-9]*x[1-9][0-9]*\.(?:png|jpe?g|webp)$")
WEEK = 7 * 86400
BASIS = "PUBLISHER_PRINTING"
KO_FIELDS = ("names", "texts", "sources", "nameBasis", "editionEvidence")
IMAGE_FIELDS = ("images", "imageSources", "imageProducts")


def image_key(value):
    if not isinstance(value, str):
        return None
    try:
        url = urlsplit(value)
        match = ART.fullmatch(url.path)
        if (url.scheme == "https" and url.netloc == "cmsassets.rgpub.io" and match):
            return match[1]
    except ValueError:
        pass
    return None


def gallery_image(card, name):
    image = card.get("cardImage") or {}
    url = image.get("url")
    label = image.get("accessibilityText")
    if (image_key(url) and isinstance(name, str) and name and isinstance(label, str) and name in label
            and urlsplit(url).query in ("", "accountingTag=RB") and not urlsplit(url).fragment):
        return url
    return None


class PageData(HTMLParser):
    def __init__(self):
        super().__init__()
        self.inside = False
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag == "script" and dict(attrs).get("id") == "__NEXT_DATA__":
            self.inside = True

    def handle_endtag(self, tag):
        if tag == "script":
            self.inside = False

    def handle_data(self, value):
        if self.inside:
            self.parts.append(value)


class RulesText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, value):
        self.parts.append(value)

    def handle_starttag(self, tag, attrs):
        if tag in ("br", "p", "li"):
            self.parts.append("\n")
        if tag == "li":
            self.parts.append("• ")

    def text(self):
        return "\n".join(line.strip() for line in "".join(self.parts).splitlines() if line.strip())


def read_gallery(path, locale, wanted):
    page_data = PageData()
    with path.open(encoding="utf-8-sig") as stream:
        for chunk in iter(lambda: stream.read(131072), ""):
            page_data.feed(chunk)
    page_data.close()
    if not page_data.parts:
        raise ValueError("Riot card gallery is missing its published page data")
    document = json.loads("".join(page_data.parts))
    page = document["props"]["pageProps"]["page"]
    if page.get("locale") != locale:
        raise ValueError("Riot card gallery returned a different locale")
    galleries = [blade for blade in page["blades"] if blade.get("type") == "riftboundCardGallery"]
    if len(galleries) != 1 or not isinstance(galleries[0]["cards"]["items"], list) or not galleries[0]["cards"]["items"]:
        raise ValueError("Riot card gallery is incomplete")
    rows = galleries[0]["cards"]["items"]
    if locale == "ko-kr" and not any(isinstance(r.get("name"), str) and HANGUL.search(r["name"]) for r in rows):
        raise ValueError("Riot Korean gallery has no localized entries")
    entries = {}
    for row in rows:
        ident = row.get("id")
        if ident not in wanted:
            continue
        if ident in entries:
            entries[ident] = None  # Reused publisher IDs are ambiguous.
            continue
        content = (row.get("text") or {}).get("richText") or {}
        text = None
        if locale == "ko-kr" and content.get("type") == "html" and isinstance(content.get("body"), str):
            parser = RulesText()
            parser.feed(content["body"])
            parser.close()
            text = parser.text()
        entries[ident] = {
            "code": row.get("publicCode"), "set": (row.get("set") or {}).get("value", {}).get("id"),
            "number": row.get("collectorNumber"), "name": row.get("name"), "subtitle": row.get("subtitle"),
            "image": image_key((row.get("cardImage") or {}).get("url")), "text": text,
            "imageUrl": gallery_image(row, row.get("name")),
        }
    return entries


def printing_identity(card):
    pack, ident = card.get("set"), card.get("riftboundId")
    if card.get("variant") == "signature" and isinstance(ident, str):
        # RiftHunt keeps '*' in the printing number and Riot's '-star-' slug in its other ID field.
        match = re.fullmatch(r"([a-z0-9]+)-([0-9]{1,4})\*-([0-9]{1,4})", ident)
        if (match and pack == match[1].upper() and card.get("num") == int(match[2])
                and card.get("id") == f"{match[1]}-{match[2]}-star-{match[3]}"):
            ident = card["id"]
    return pack, ident, image_key(card.get("imgUrl"))


def galleries(http, printings):
    wanted = {ident for _, ident, asset in map(printing_identity, printings) if ident and asset}
    if not wanted:
        return {}, {}
    try:
        robot = RobotFileParser()
        robot.parse(http.get(ORIGIN + "/robots.txt", ttl=86400).read_text("utf-8-sig").splitlines())
        if not all(robot.can_fetch("TCGHub-Catalog", url) for url in GALLERIES.values()):
            raise ValueError("Robots policy disallows a regional card gallery")
        delay = max(1, robot.crawl_delay("TCGHub-Catalog") or 0)
        rate = robot.request_rate("TCGHub-Catalog")
        if rate:
            delay = max(delay, rate.seconds / rate.requests)
        return tuple(read_gallery(http.get(url, ttl=WEEK, size=16_000_000, delay=delay), locale, wanted)
                     for locale, url in GALLERIES.items())
    except HTTPError as exc:
        if exc.code in (429, 503):
            raise  # The existing scheduler honors Retry-After.
        logging.getLogger(__name__).warning("Riot regional catalog unavailable (HTTP %d)", exc.code)
        exc.close()
    except (OSError, ValueError, KeyError, TypeError) as exc:
        logging.getLogger(__name__).warning("Riot regional catalog incomplete (%s)", type(exc).__name__)
    return {}, {}


def add_korean_edition(record, card, indexes, unique):
    pack, ident, asset = printing_identity(card)
    if not ident or not asset or unique[(pack, ident, asset)] != 1:
        return
    en_index, ko_index = indexes
    # A partially rendered gallery can omit an otherwise verified printing. Carry it
    # over only while the underlying English printing and source asset still match.
    if ident not in en_index or ident not in ko_index:
        record["_deferred_riot_edition"] = {"publisherId": ident, "set": pack,
                                            "collectorNumber": card.get("num"), "englishImageKey": asset}
        return
    en, ko = en_index[ident], ko_index[ident]
    if (not en or not ko or not en["code"] or en["code"] != ko["code"] or
            en["set"] != pack or ko["set"] != pack or card.get("num") is None or
            en["number"] != card["num"] or ko["number"] != card["num"] or en["image"] != asset):
        return
    if ident != card["riftboundId"]:
        number, total = card["riftboundId"].upper().rsplit("-", 1)
        if en["code"] != f"{number}/{total}":
            return
    name = ko["name"]
    if not isinstance(name, str) or not HANGUL.search(name):
        return  # Korean gallery pages also include unreleased cards in English.
    name = name.strip()
    # On spells, the subtitle can name a champion and is not part of the printed
    # name. Combine subtitles only when the English printing includes that subtitle.
    if en["subtitle"] and ko["subtitle"] and HANGUL.search(ko["subtitle"]):
        full = f"{en['name']}, {en['subtitle']}"
        if full.casefold() == str(card.get("cleanName") or "").casefold():
            name = f"{name}, {ko['subtitle']}"
    specs = record["specs"]
    specs["productCode"] = pack
    images = {}
    if en["imageUrl"]:
        images["en"] = en["imageUrl"]
    if ko["imageUrl"] and ko["image"] != en["image"]:
        images["ko"] = ko["imageUrl"]
    if images:
        specs["images"] = images
        specs["imageProducts"] = {lang: pack for lang in images}
        specs["imageSources"] = {lang: GALLERIES["ko-kr" if lang == "ko" else "en-us"] for lang in images}
    specs["names"] = {"ko": name}
    if ko["text"] and HANGUL.search(ko["text"]):
        specs["texts"] = {"ko": ko["text"]}
    specs["nameBasis"] = {"ko": "PRINTED_NAME"}
    specs["sources"] = {"ko": GALLERIES["ko-kr"]}
    specs["editionEvidence"] = {"ko": {
        "basis": BASIS, "publisherId": ident, "set": pack, "publicCode": en["code"],
        "collectorNumber": card["num"], "englishImageKey": asset,
        "englishSource": GALLERIES["en-us"], "source": GALLERIES["ko-kr"],
    }}


def preserve_deferred(db, cards):
    pending = {key: item for key, item in cards.items() if item.get("_deferred_riot_edition")}
    if not pending:
        return
    for key, prior in db.execute("SELECT legacy_key,specs FROM card WHERE legacy_key=ANY(%s)", (list(pending),)):
        item = pending[key]
        evidence = prior.get("editionEvidence")
        saved = evidence.get("ko") if isinstance(evidence, dict) else None
        if (not isinstance(saved, dict) or saved.get("basis") != BASIS
                or any(saved.get(k) != v for k, v in item["_deferred_riot_edition"].items())):
            continue
        for field in KO_FIELDS:
            if isinstance(prior.get(field), dict) and "ko" in prior[field]:
                item["specs"].setdefault(field, {})["ko"] = prior[field]["ko"]
        if prior.get("productCode") == saved["set"]:
            item["specs"]["productCode"] = saved["set"]
            for field in IMAGE_FIELDS:
                if isinstance(prior.get(field), dict):
                    for lang in ("en", "ko"):
                        if lang in prior[field]:
                            item["specs"].setdefault(field, {})[lang] = prior[field][lang]
