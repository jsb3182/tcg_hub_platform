"""Discover official card-image references and publish bounded, local WebP batches."""
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import io
from http.client import HTTPException
from pathlib import PurePosixPath
import re
import shutil
import time
from urllib.error import HTTPError
from urllib.parse import quote, unquote, urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from urllib.robotparser import RobotFileParser

from PIL import Image, ImageOps
from psycopg.types.json import Jsonb
from bs4 import BeautifulSoup

from .jobs import connect
from .media import LIMIT_BYTES, LIMIT_PIXELS, publish


GAMES = ("YUGIOH", "POKEMON", "WEISS", "NIVEL", "RIFTBOUND", "ONEPIECE")
LOCK = 73401856
AGENT = "TCGHub-Catalog"
_POLICIES = {}
PATHS = {
    "artworks-ko-db.ygoresources.com": r"/\d+/\d+/\d+_\d+\.png",
    "artworks-en-n.ygoresources.com": r"/\d+/\d+/\d+_\d+\.png",
    "artworks-jp-n.ygoresources.com": r"/\d+/\d+/\d+_\d+\.png",
    "www.pokemon-card.com": r"/assets/images/card_images/(?:large|small)/[^?#]+\.(?:png|jpg)",
    "cards.image.pokemonkorea.co.kr": r"/data/wmimages/[^?#]+\.(?:png|jpe?g|webp)",
    "pokemoncard.co.kr": r"/public-assets/home/data/cards.image_www/data/wmimages/[^?#]+\.webp",
    "images.pokemontcg.io": r"/[A-Za-z0-9._-]+/[A-Za-z0-9._-]+\.png",
    "assets.tcgdex.net": r"/(?:en|ja|ko)/[A-Za-z0-9._/-]+/(?:high|low)\.(?:webp|png|jpg)",
    "en.onepiece-cardgame.com": r"/images/cardlist/card/[A-Za-z0-9_-]+\.png",
    "www.onepiece-cardgame.com": r"/images/cardlist/card/[A-Za-z0-9_-]+\.png",
    "optcgapi.com": r"/media/static/Card_Images/[^?#]+\.(?:png|jpe?g|webp)",
    "www.optcgapi.com": r"/media/static/Card_Images/[^?#]+\.(?:png|jpe?g|webp)",
    "cmsassets.rgpub.io": r"/sanity/images/dsfx7636/game_data_live/[0-9a-f]{40}-\d+x\d+\.(?:png|jpe?g|webp)",
    "www.onepiece-cardgame.kr": r"/fileDownload",
    "en.ws-tcg.com": r"/(?:wordpress|wp)/wp-content/images/cardimages/[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+\.(?:png|jpe?g|webp)",
    "nivelarena.co.kr": r"/data/file/cardlists/[A-Za-z0-9_-]+\.(?:png|jpe?g|webp)",
}


def provider(url):
    if not isinstance(url, str) or len(url) > 2048:
        return None
    try:
        parts = urlsplit(url)
        host = parts.netloc
        path = unquote(parts.path, errors="strict")
    except (ValueError, UnicodeError):
        return None
    accepted_scheme = parts.scheme == "https" or (host == "nivelarena.co.kr" and parts.scheme == "http")
    if (not accepted_scheme or parts.fragment or host not in PATHS or "\\" in path
            or any(v in (".", "..") for v in path.split("/")) or any(ord(v) < 32 for v in url + path)):
        return None
    if not re.fullmatch(PATHS[host], path, re.IGNORECASE):
        return None
    if host == "www.onepiece-cardgame.kr":
        return host if re.fullmatch(r"downname=[A-Za-z0-9_-]{8,128}", parts.query) else None
    if host == "pokemoncard.co.kr":
        return host if parts.query in ("", "w=512") else None
    if parts.query and not (host == "cmsassets.rgpub.io" and parts.query == "accountingTag=RB"):
        return None
    return host


def webp(data):
    if not data or len(data) > LIMIT_BYTES:
        raise ValueError("Invalid source size")
    with Image.open(io.BytesIO(data), formats=["JPEG", "PNG", "WEBP"]) as im:
        if im.width * im.height > LIMIT_PIXELS or getattr(im, "n_frames", 1) != 1:
            raise ValueError("Invalid image dimensions or frame count")
        im.verify()
    with Image.open(io.BytesIO(data), formats=["JPEG", "PNG", "WEBP"]) as source:
        # Downsample JPEG on decode where possible; preserve card edges and aspect ratio.
        source.draft("RGB", (480, 700))
        im = ImageOps.exif_transpose(source)
        im.thumbnail((480, 700), Image.Resampling.LANCZOS)
        pixel_data = im.convert("RGBA" if "A" in im.getbands() or "transparency" in im.info else "RGB")
        output = io.BytesIO()
        pixel_data.save(output, "WEBP", quality=80, method=4)
        return output.getvalue()


def capture_hash(encoded):
    with Image.open(io.BytesIO(encoded), formats=["WEBP"]) as image:
        if image.width * image.height > LIMIT_PIXELS or image.n_frames != 1:
            raise ValueError("Invalid cached artwork")
        rgb = image.convert("RGB")
        bits = []
        for j in range(8):
            y = rgb.height * (190 + 65*j) // 1000
            lum = []
            for i in range(9):
                x = rgb.width * (120 + 95*i) // 1000
                red, green, blue = rgb.getpixel((x,y))
                lum.append((299*red + 587*green + 114*blue) // 1000)
            bits.extend("1" if left>right else "0" for left,right in zip(lum,lum[1:]))
        return "".join(bits)


def backfill_hashes(db, media):
    rows = db.execute("""SELECT id,storage_key FROM catalog_art_file
                         WHERE capture_hash IS NULL AND storage_key IS NOT NULL ORDER BY id LIMIT 12""").fetchall()
    for file_id, key in rows:
        path = media / key
        try:
            with path.open("rb") as stream:
                data = stream.read(LIMIT_BYTES+1)
            if len(data)>LIMIT_BYTES or path.stem!=hashlib.sha256(data).hexdigest():
                raise ValueError("Invalid cached artwork")
            fingerprint = capture_hash(data)
        except (OSError, ValueError, SyntaxError, Image.DecompressionBombError):
            db.execute("""UPDATE catalog_art_file SET storage_key=NULL,source_sha256=NULL,
                next_attempt=now(),last_error='Missing or damaged cached artwork' WHERE id=%s AND storage_key=%s""",
                       (file_id,key))
            continue
        db.execute("UPDATE catalog_art_file SET capture_hash=%s::bit(64) WHERE id=%s AND storage_key=%s",
                   (fingerprint,file_id,key))


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def site_delay(url):
    parts = urlsplit(url)
    origin = f"{parts.scheme}://{parts.netloc}"
    cached = _POLICIES.get(origin)
    if not cached or cached[0] <= time.monotonic():
        rules = RobotFileParser()
        try:
            req = Request(origin + "/robots.txt", headers={"User-Agent": AGENT + "/1.0"})
            with build_opener(NoRedirect).open(req, timeout=6) as response:
                block = response.read(256 * 1024 + 1)
                if len(block) > 256 * 1024:
                    raise ValueError("Provider policy too large")
                rules.parse(block.decode("utf-8-sig", errors="replace").splitlines())
        except HTTPError as error:
            if error.code == 404:
                rules.parse([])
            elif error.code in (401, 403):
                rules.disallow_all = True
            else:
                raise
            error.close()
        cached = (time.monotonic() + 86400, rules)
        _POLICIES[origin] = cached
    rules = cached[1]
    if not rules.can_fetch(AGENT, url):
        raise PermissionError("Provider disallows image downloads")
    rate = rules.request_rate(AGENT)
    return max(3, rules.crawl_delay(AGENT) or 0, (rate.seconds + rate.requests - 1) // rate.requests if rate else 0)


def download(url):
    if not provider(url):
        raise ValueError("Image source is outside the provider policy")
    request = Request(url, headers={"User-Agent": "TCGHub-Catalog/1.0", "Accept": "image/webp,image/png,image/jpeg"})
    deadline = time.monotonic() + 25
    opener = build_opener(NoRedirect)
    try:
        stream = opener.open(request, timeout=8)
    except HTTPError as error:
        # The Weiss maintainer's archived paths redirect to Bushiroad's current image tree.
        target = urljoin(url, error.headers.get("Location", ""))
        if (error.code not in (301,302,307,308) or provider(url) != "en.ws-tcg.com"
                or provider(target) != "en.ws-tcg.com" or target == url):
            raise
        error.close()
        time.sleep(site_delay(target))
        stream = opener.open(Request(target, headers=dict(request.header_items())), timeout=8)
    with stream as response:
        size = response.headers.get("Content-Length")
        if size is not None and (not size.isdecimal() or int(size) > LIMIT_BYTES):
            raise ValueError("Invalid source size")
        data = bytearray()
        while time.monotonic() < deadline:
            part = response.read1(min(65536, LIMIT_BYTES + 1 - len(data)))
            if not part:
                return bytes(data)
            data.extend(part)
            if len(data) > LIMIT_BYTES:
                raise ValueError("Source too large")
    raise TimeoutError("Source time limit")


def pokemon_target(html, page, old_url):
    images = BeautifulSoup(html, "html.parser").select("img.feature_image[src]")
    if len(images) != 1:
        return None
    target = urljoin(page, images[0]["src"])
    if provider(target) != "pokemoncard.co.kr":
        return None
    relative = urlsplit(target).path.removeprefix("/public-assets/home/data/cards.image_www")
    if PurePosixPath(relative).with_suffix("") != PurePosixPath(urlsplit(old_url).path).with_suffix(""):
        return None
    return target


def detail_html(page):
    req = Request(page, headers={"User-Agent": AGENT + "/1.0"})
    with build_opener(NoRedirect).open(req, timeout=8) as response:
        html = response.read(512_001)
        if len(html)>512_000:
            raise ValueError("Publisher detail too large")
    return html


def replacement(db, file_id, old_url, game):
    rows = db.execute("""
        SELECT DISTINCT c.source_url,c.number,c.legacy_key FROM catalog_art_card a JOIN card c ON c.id=a.card_id
        WHERE a.file_id=%s AND c.game_code=%s AND c.status='PUBLISHED' AND c.specs->'images'->>%s=%s
        LIMIT 2""", (file_id, game, "ko" if game=="POKEMON" else "en", old_url)).fetchall()
    if len(rows) != 1:
        return None
    source, number, ident = rows[0]
    if game=="POKEMON":
        match = re.fullmatch(r"https://pokemoncard\.co\.kr/cards/detail/([A-Za-z0-9_-]+)", source or "")
        if not match or ident!="catalog:POKEMON:ko:"+match[1]:
            return None
        page = source
    else:
        if ident!="catalog:WEISS:en:"+number or source!="https://en.ws-tcg.com/cardlist/cardsearch/exec?cardno="+quote(number,safe=""):
            return None
        page = "https://en.ws-tcg.com/cardlist/?cardno="+quote(number,safe="")
    delay = site_delay(page)
    if delay>15:
        return None
    time.sleep(delay)
    html = detail_html(page)
    if game=="POKEMON":
        target = pokemon_target(html,page,old_url)
    else:
        body = BeautifulSoup(html, "html.parser")
        printed = body.select_one(".p-cards__detail-textarea .number")
        images = [urljoin(page, i["src"]) for i in body.select(".image img[src]")]
        images = [url for url in images if provider(url)=="en.ws-tcg.com"
                  and urlsplit(url).path.split("/cardimages/")[-1]==urlsplit(old_url).path.split("/cardimages/")[-1]]
        if not printed or number not in printed.stripped_strings or len(set(images))!=1:
            return None
        target = images[0]
    if target:
        spacing = max(delay, site_delay(target))
        if spacing>15:
            return None
        time.sleep(spacing)
    return target


def pace(db, host, seconds):
    db.execute("""
        INSERT INTO catalog_art_host VALUES (%s,now()+%s*interval '1 second')
        ON CONFLICT(hostname) DO UPDATE SET next_attempt=greatest(catalog_art_host.next_attempt,excluded.next_attempt)
        """, (host, seconds))


def discover(db, game, size):
    with db.transaction():
        after = db.execute("SELECT after_id FROM catalog_art_scan WHERE game_code=%s", (game,)).fetchone()
        rows = db.execute("""
            WITH picked AS MATERIALIZED (
                SELECT id,specs,legacy_key,number,original_name FROM card
                 WHERE game_code=%s AND id>%s AND status='PUBLISHED' ORDER BY id LIMIT %s FOR SHARE)
            SELECT p.id,p.specs->'images',a.ko_path,a.en_path,a.ja_path,
                 ARRAY(SELECT n.image_path FROM neuron_artwork n
                       WHERE %s='YUGIOH' AND n.cid=coalesce(p.specs->>'konami_id',e.konami_id::text))
            FROM picked p LEFT JOIN legacy_card_edition e ON e.card_id=p.id
                 AND e.matched_number=p.number AND e.matched_name=p.original_name
            LEFT JOIN yugioh_reference_art a ON %s='YUGIOH' AND a.cid=coalesce(p.specs->>'konami_id',e.konami_id::text)
            ORDER BY p.id
            """, (game, after[0] if after else 0, size, game,game)).fetchall()
        associations = []
        for cid, images, ko, en, ja, art in rows:
            urls = {value for lang, value in images.items() if lang in ("ko","en","ja") and isinstance(value, str)} if isinstance(images, dict) else set()
            for path, subdomain in ((ko,"ko-db"), (en,"en-n"), (ja,"jp-n"), *((p,"jp-n") for p in art)):
                if path:
                    urls.add(f"https://artworks-{subdomain}.ygoresources.com" + path)
            associations.extend({"card_id": cid, "url": url} for url in sorted(urls) if provider(url))
        links = Jsonb(associations)
        if associations:
            db.execute("""
                INSERT INTO catalog_art_file(game_code,source_url)
                    SELECT DISTINCT %s,item->>'url' FROM jsonb_array_elements(%s) item
                    ON CONFLICT(source_url) DO NOTHING""", (game, links))
            db.execute("""
                INSERT INTO catalog_art_card(card_id,file_id)
                    SELECT r.card_id,f.id FROM jsonb_to_recordset(%s) r(card_id bigint,url text)
                    JOIN catalog_art_file f ON f.source_url=r.url ON CONFLICT DO NOTHING""", (links,))
        if rows:
            db.execute("""
                DELETE FROM catalog_art_card a USING catalog_art_file f WHERE a.file_id=f.id AND a.card_id=ANY(%s)
                    AND NOT EXISTS (SELECT FROM jsonb_to_recordset(%s) r(card_id bigint,url text)
                                    WHERE r.card_id=a.card_id AND r.url=f.source_url)
                """, ([r[0] for r in rows], links))
        db.execute("""
            INSERT INTO catalog_art_scan VALUES (%s,%s) ON CONFLICT(game_code) DO UPDATE SET after_id=excluded.after_id
            """, (game, rows[-1][0] if len(rows) == size else 0))


def delay_after(value):
    if value and value.isdecimal():
        return min(int(value), 2147483647)
    if value:
        try:
            return max(1, int((parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds()) + 1)
        except (TypeError, ValueError, OverflowError):
            pass
    return 3600


def batch(db, media, stop, games=GAMES, scan=96, fetch=download, policy=site_delay):
    if not db.execute("SELECT pg_try_advisory_lock(%s)", (LOCK,)).fetchone()[0]:
        return 0
    done = 0
    try:
        media.mkdir(parents=True, exist_ok=True)
        backfill_hashes(db,media)
        for game in games:
            if stop.is_set():
                break
            discover(db, game, scan)
            if shutil.disk_usage(media).free < 768 * 1024 * 1024:
                continue
            row = db.execute("""
                SELECT f.id,f.source_url,f.failures FROM catalog_art_file f
                 WHERE f.game_code=%s AND f.next_attempt<=now()
                   AND EXISTS (SELECT FROM catalog_art_card a JOIN card c ON c.id=a.card_id
                               WHERE a.file_id=f.id AND c.status='PUBLISHED')
                   AND NOT EXISTS (SELECT FROM catalog_art_host h WHERE h.hostname=split_part(f.source_url,'/',3)
                                   AND h.next_attempt>now())
                 ORDER BY f.next_attempt,f.id LIMIT 1""", (game,)).fetchone()
            if not row:
                continue
            file_id, url, failures = row
            host = provider(url)
            try:
                if not host:
                    raise ValueError("Provider not approved")
                delay = max(3, policy(url))
                pace(db, host, delay)
                try:
                    original = fetch(url)
                except HTTPError as missing:
                    moved_pokemon = host=="cards.image.pokemonkorea.co.kr" and missing.code==404
                    moved_weiss = host=="en.ws-tcg.com" and missing.code in (301,302,307,308,404)
                    if not (moved_pokemon or moved_weiss):
                        raise
                    if moved_pokemon and db.execute("SELECT EXISTS (SELECT FROM catalog_art_host WHERE hostname='pokemoncard.co.kr' AND next_attempt>now())").fetchone()[0]:
                        raise
                    host = "pokemoncard.co.kr" if moved_pokemon else host
                    pace(db,host,3)
                    target = replacement(db, file_id, url, game)
                    if not target:
                        raise
                    missing.close()
                    pace(db, host, policy(target))
                    original = fetch(target)
                data = webp(original)
                key = publish(media, "cards", data)
                db.execute("""
                    UPDATE catalog_art_file SET storage_key=%s,source_sha256=%s,capture_hash=%s::bit(64),checked_at=now(),
                        next_attempt=now()+interval '90 days',failures=0,last_error=NULL WHERE id=%s
                    """, (key, hashlib.sha256(original).hexdigest(), capture_hash(data), file_id))
                done += 1
            except (OSError, ValueError, SyntaxError, HTTPException, Image.DecompressionBombError) as error:
                delay = min(7*86400, 3600*2**min(failures, 8))
                why = type(error).__name__
                if isinstance(error, HTTPError):
                    why = f"HTTP {error.code}"
                    if error.code in (429, 503):
                        delay = max(delay, delay_after(error.headers.get("Retry-After")))
                        pace(db, host, delay)
                    if error.code in (403, 404, 410):
                        delay = max(delay, 7*86400)
                    error.close()
                db.execute("""UPDATE catalog_art_file SET last_error=%s,failures=failures+1,
                    next_attempt=now()+%s*interval '1 second' WHERE id=%s""", (why, delay, file_id))
    finally:
        db.execute("SELECT pg_advisory_unlock(%s)", (LOCK,))
    return done


def scheduled(media, stop):
    with connect() as db:
        db.autocommit = True
        return batch(db, media, stop)
