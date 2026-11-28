"""English printing and publisher references. These URLs do not authorize caching an image."""
import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path, PurePosixPath
from urllib.parse import quote, urljoin, urlsplit

from bs4 import BeautifulSoup

ORIGIN = "https://en.ws-tcg.com"
REPOSITORY = "CCondeluci/WeissSchwarz-ENG-DB"
IMAGE_PATH = re.compile(
    r"/(?:(?:wordpress|wp)/wp-content/images/cardimages/|cardlist/cardimages/)"
    r"(?:[A-Za-z0-9_-]+/){0,3}[A-Za-z0-9_-][A-Za-z0-9_.() -]{0,180}\.(?:png|jpe?g)", re.I)


def card_page(code):
    return ORIGIN + "/cardlist/?cardno=" + quote(code, safe="")


def sets(archive):
    for entry in archive.infolist():
        parts = PurePosixPath(entry.filename).parts
        if len(parts) != 3 or parts[1] != "DB" or not parts[2].endswith(".json"):
            continue
        if entry.file_size > 10_000_000:
            raise ValueError("Unexpected Weiss set file size")
        with archive.open(entry) as stream:
            yield parts[2], json.load(stream)


def conflicting_prints(archive):
    """A reused image pointer or a conflicting duplicate card number needs direct confirmation."""
    owner, source, ambiguous = {}, {}, set()
    for _, cards in sets(archive):
        for card in cards:
            image = reference_image(card.get("image"))
            if image:
                code = card["code"].strip()
                prior = owner.setdefault(image, code)
                if prior != code:
                    ambiguous.update((code, prior))
                if source.setdefault(code, image) != image:
                    ambiguous.add(code)
    return ambiguous


def reference_image(value):
    """Accept a literal issuer image path in a source row, never derive one from a card number."""
    if not isinstance(value, str) or not value.startswith(ORIGIN + "/") or len(value) > 768:
        return None
    if any(ord(c) < 32 for c in value) or any(c in value for c in ("%", "\\", "?", "#")):
        return None
    parts = urlsplit(value)
    if not IMAGE_PATH.fullmatch(parts.path) or ".." in parts.path:
        return None
    return ORIGIN + quote(parts.path, safe="/._-()")


def from_detail(card, raw, observed):
    """Reproduce the published reference from issuer HTML, without requesting image bytes."""
    body = BeautifulSoup(raw, "html.parser")
    wrappers = body.select(".p-cards__detail-wrapper-inner")
    if len(wrappers) != 1:
        return None
    wrapper = wrappers[0]
    def exact(selector, expected):
        fields = wrapper.select(selector)
        return len(fields) == 1 and bool(expected) and fields[0].get_text(" ", strip=True) == expected

    if not exact(".p-cards__detail-textarea .number", card["code"]) or not exact(".p-cards__detail-textarea .ttl", card["name"]):
        return None
    titles = [item.select_one("dd").get_text(" ", strip=True) for item in wrapper.select(".p-cards__detail-type dl")
              if item.select_one("dt") and item.select_one("dt").get_text(" ", strip=True) == "Expansion" and item.select_one("dd")]
    if titles != [card.get("expansion")]:
        return None
    images = {reference_image(urljoin(ORIGIN, el["src"])) for el in wrapper.select(".image img[src]")}
    if len(images) != 1 or None in images:
        return None
    return {"code": card["code"], "name": card["name"], "expansion": card["expansion"],
            "imageUrl": images.pop(), "observedOn": observed, "htmlSha256": hashlib.sha256(raw).hexdigest()}


@lru_cache(maxsize=1)
def reviewed_pages():
    records = json.loads(Path(__file__).with_name("weiss_reviewed_images.json").read_text("utf8"))
    return {r["code"]: r for r in records}


def metadata(card, revision, filename, ambiguous):
    code, name = card["code"].strip(), card["name"].strip()
    page = card_page(code)
    result = {"publisherCardUrl": page}
    checked = reviewed_pages().get(code)
    if checked and (name, card.get("expansion")) == (checked["name"], checked["expansion"]):
        image = reference_image(checked["imageUrl"])
        if image:
            result["publisherArtwork"] = {"en": {"printingNumber": code, "cardUrl": page, "imageUrl": image,
                "basis": "PUBLISHER_CARD_DETAIL", "sourceUrl": page, "observedOn": checked["observedOn"],
                "htmlSha256": checked["htmlSha256"]}}
            return result

    image = reference_image(card.get("image"))
    if not image or code in ambiguous:
        return result
    # Some English rows refer to event artwork with a distinctly different release year.
    years = set(re.findall(r"(?:19|20)[0-9]{2}", code))
    image_years = set(re.findall(r"(?:19|20)[0-9]{2}", image.rsplit("/", 1)[-1]))
    if years and image_years and years.isdisjoint(image_years):
        return result
    result["publisherArtwork"] = {"en": {"printingNumber": code, "cardUrl": page, "imageUrl": image,
        "basis": "MAINTAINER_PRINTING_REFERENCE", "sourceRevision": revision,
        "sourceUrl": f"https://github.com/{REPOSITORY}/blob/{revision}/DB/" + quote(filename, safe="")}}
    return result
