"""Match RiftHunt printings to Riot's English and Korean public card galleries."""
import json
import logging
import re
from html.parser import HTMLParser
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser


ORIGIN = "https://playriftbound.com"
RIOT_CONTENT = "https://asia.api.riotgames.com/riftbound/content/v1/contents"
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


def publisher_image_url(value):
    if not image_key(value) or len(value) > 512 or any(char.isspace() or ord(char) < 32 for char in value):
        return None
    url = urlsplit(value)
    return value if url.query in ("", "accountingTag=RB") and not url.fragment else None


def gallery_image(card, name):
    image = card.get("cardImage") or {}
    url = image.get("url")
    label = image.get("accessibilityText")
    if isinstance(name, str) and name and isinstance(label, str) and name in label:
        return publisher_image_url(url)
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
        delay = max(1, robot.crawl_delay("TCGHub-Catalog") or 0)
        rate = robot.request_rate("TCGHub-Catalog")
        if rate:
            delay = max(delay, rate.seconds / rate.requests)
    except HTTPError as exc:
        if exc.code in (429, 503):
            raise  # The existing scheduler honors Retry-After.
        logging.getLogger(__name__).warning("Riot regional catalog unavailable (HTTP %d)", exc.code)
        exc.close()
        return {}, {}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        logging.getLogger(__name__).warning("Riot regional catalog incomplete (%s)", type(exc).__name__)
        return {}, {}
    indexes = {}
    for locale, url in GALLERIES.items():
        indexes[locale] = {}
        if not robot.can_fetch("TCGHub-Catalog", url):
            continue
        try:
            page = http.get(url, ttl=WEEK, size=16_000_000, delay=delay)
            indexes[locale] = read_gallery(page, locale, wanted)
        except HTTPError as exc:
            if exc.code in (429, 503):
                raise
            logging.getLogger(__name__).warning("Riot %s catalog unavailable (HTTP %d)", locale, exc.code)
            exc.close()
        except (OSError, ValueError, KeyError, TypeError) as exc:
            logging.getLogger(__name__).warning("Riot %s catalog incomplete (%s)", locale, type(exc).__name__)
    return indexes["en-us"], indexes["ko-kr"]


def add_korean_edition(record, card, indexes, unique):
    pack, ident, asset = printing_identity(card)
    if not ident or not asset or unique[(pack, ident, asset)] != 1:
        return
    en_index, ko_index = indexes
    proof = {"publisherId": ident, "set": pack, "collectorNumber": card.get("num"), "englishImageKey": asset}
    en = en_index.get(ident)
    if ident in en_index:
        number = card.get("riftboundId")
        if (not en or not isinstance(number, str) or not isinstance(en["code"], str)
                or en["code"].casefold().replace("/", "-") != number.casefold()
                or en["set"] != pack or type(card.get("num")) is not int
                or en["number"] != card["num"] or en["image"] != asset):
            return
        if en["imageUrl"]:
            # Gallery evidence identifies a printing. It alone does not authorize a new image download.
            record["specs"]["editionEvidence"] = {"en": {
                **proof, "basis": BASIS, "publicCode": en["code"], "source": GALLERIES["en-us"],
                "imageFile": urlsplit(en["imageUrl"]).path.rsplit("/", 1)[1],
            }}
    # A partially rendered gallery can omit an otherwise verified printing. Carry it
    # over only while the underlying English printing and source asset still match.
    if ident not in en_index or ident not in ko_index:
        record["_deferred_riot_edition"] = proof
        return
    ko = ko_index[ident]
    if not ko or en["code"] != ko["code"] or ko["set"] != pack or ko["number"] != card["num"]:
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
    specs.setdefault("editionEvidence", {})["ko"] = {
        "basis": BASIS, "publisherId": ident, "set": pack, "publicCode": en["code"],
        "collectorNumber": card["num"], "englishImageKey": asset,
        "englishSource": GALLERIES["en-us"], "source": GALLERIES["ko-kr"],
    }


def preserve_deferred(db, cards):
    pending = {key: item for key, item in cards.items() if item.get("_deferred_riot_edition")}
    if not pending:
        return
    for key, prior in db.execute("SELECT legacy_key,specs FROM card WHERE legacy_key=ANY(%s)", (list(pending),)):
        item = pending[key]
        evidence = prior.get("editionEvidence")
        english = evidence.get("en") if isinstance(evidence, dict) else None
        if (isinstance(english, dict) and english.get("basis") == BASIS
                and all(english.get(k) == v for k, v in item["_deferred_riot_edition"].items())):
            item["specs"].setdefault("editionEvidence", {}).setdefault("en", english)
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


def attach_riot_api_art(db, cards):
    """Use an absolute URL supplied by the authenticated content feed for this exact English face."""
    wanted = {}
    for item in cards.values():
        specs = item["specs"]
        en = specs.get("editionEvidence", {}).get("en", {})
        if en.get("basis") != BASIS or not en.get("imageFile"):
            continue
        for ident in {en["publisherId"], item["number"]}:
            wanted.setdefault(ident, []).append(item)
    if not wanted:
        return
    observations = db.execute("""
        SELECT external_id,pack_code,number,facts FROM supplemental_printing
        WHERE provider='RIOT' AND game_code='RIFTBOUND' AND lang='en' AND source_url=%s
        AND external_id=ANY(%s) AND facts ? 'artUrls' ORDER BY external_id
        """, (RIOT_CONTENT, list(wanted)))
    for ident, pack, number, facts in observations:
        if number != ident.lower() or not isinstance(facts.get("artUrls"), list):
            continue
        for item in wanted[ident]:
            specs = item["specs"]
            en = specs["editionEvidence"]["en"]
            collector = facts.get("collectorNumber")
            if (pack != en["set"] or type(collector) is not int
                    or collector != en["collectorNumber"]):
                continue
            for url in facts["artUrls"]:
                if (publisher_image_url(url) and image_key(url) == en["englishImageKey"]
                        and specs.get("images", {}).get("en", url) == url
                        and urlsplit(url).path.rsplit("/", 1)[1] == en["imageFile"]):
                    specs.setdefault("images", {})["en"] = url
                    specs.setdefault("imageProducts", {})["en"] = pack
                    specs.setdefault("imageSources", {})["en"] = RIOT_CONTENT
                    specs["productCode"] = pack
                    break
