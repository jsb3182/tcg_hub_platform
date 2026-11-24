"""Read the exported static catalogue as JSON data, without executing any JavaScript."""
import hashlib
import io
import json
import re
from datetime import date
from pathlib import Path

from PIL import Image

from .media import COLUMNS, ROWS, publish


def records(source: Path) -> list[dict]:
    source_text = (source / "js" / "app.js").read_text(encoding="utf-8-sig")
    start = re.match(r"\s*var\s+ITEMS\s*=\s*", source_text)
    if not start:
        raise ValueError("Expected js/app.js to start with var ITEMS")
    packs, end = json.JSONDecoder().raw_decode(source_text, start.end())
    if not isinstance(packs, list) or not source_text[end:].lstrip().startswith(";"):
        raise ValueError("Expected a JSON array followed by a semicolon")
    if len({p["id"] for p in packs}) != len(packs):
        raise ValueError("Duplicate legacy section ID")
    return packs


def variants(card):
    alternatives = card.get("il")
    if alternatives:
        return alternatives
    return [{"im": card.get("im"), "r": card.get("r")}]


def entry_key(card, ordinal):
    return f"xid:{card['xid']}" if card.get("xid") else f"row:{ordinal}"


def sheet_files(source: Path) -> dict[int, Path]:
    files = {}
    for path in sorted((source / "imgd").glob("d*.webp")):
        match = re.fullmatch(r"d(\d+)\.webp", path.name)
        if match:
            number = int(match.group(1))
            if number in files:
                raise ValueError(f"Duplicate legacy sheet {number}")
            files[number] = path
    return files


def read_webp(path: Path):
    data = path.read_bytes()
    with Image.open(io.BytesIO(data), formats=["WEBP"]) as image:
        if image.n_frames != 1:
            raise ValueError(f"Animated legacy image {path.name}")
        image.load()
        return data, image.size


def banner_path(source: Path, name: str) -> Path:
    if not re.fullmatch(r"pk/[a-zA-Z0-9_-]+\.webp", name):
        raise ValueError("Unexpected legacy banner path")
    return source / name


def check(source: Path):
    packs = records(source)
    sheets = sheet_files(source)
    assets = {}
    for path in sheets.values():
        data, (width, height) = read_webp(path)
        assets[path.relative_to(source).as_posix()] = hashlib.sha256(data).hexdigest()
        if width % COLUMNS or height % ROWS:
            raise ValueError(f"Invalid legacy grid {path.name}")
    cards = images = missing = 0
    unresolved = []
    banners = set()
    for pack in packs:
        if pack.get("bg"):
            if pack["bg"] not in banners:
                data, _ = read_webp(banner_path(source, pack["bg"]))
                assets[pack["bg"]] = hashlib.sha256(data).hexdigest()
                banners.add(pack["bg"])
        for ordinal, card in enumerate(pack["cards"]):
            cards += 1
            if not card.get("n") and not card.get("on"):
                raise ValueError("Missing both card names")
            found = False
            for variant in variants(card):
                coords = variant.get("im")
                if coords is None:
                    continue
                index, col, row = coords
                if index not in sheets or not (0 <= col < COLUMNS and 0 <= row < ROWS):
                    raise ValueError(f"Unknown atlas coordinate {coords}")
                found = True
                images += 1
            if not found:
                missing += 1
                if card.get("img"):
                    unresolved.append({"section_id": pack["id"], "entry_key": entry_key(card, ordinal),
                                       "reason": "legacy_image_reference_without_sheet"})
    snapshot_hash = hashlib.sha256((source / "js" / "app.js").read_bytes()).hexdigest()
    manifest = json.dumps(assets, sort_keys=True, separators=(",", ":")).encode()
    return {"packs": len(packs), "cards": cards, "sheets": len(sheets), "banners": len(banners),
            "source_app_sha256": snapshot_hash,
            "source_assets_sha256": hashlib.sha256(manifest).hexdigest(),
            "variants_with_images": images, "cards_without_images": missing, "unresolved_images": unresolved}


def exact_date(value):
    return date.fromisoformat(value) if value and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) else None


def import_catalog(db, source: Path, root: Path):
    from psycopg.types.json import Jsonb

    stats = check(source)
    pack_rows = records(source)
    with db.transaction():
        db.execute("SELECT pg_advisory_xact_lock(83269432)")
        sheet_ids = {}
        for index, path in sheet_files(source).items():
            data, (width, height) = read_webp(path)
            key = publish(root, "sheets", data)
            sheet_ids[index] = db.execute(
                """INSERT INTO image_sheet(storage_key,cell_width,cell_height) VALUES (%s,%s,%s)
                   ON CONFLICT(storage_key) DO UPDATE SET storage_key=EXCLUDED.storage_key RETURNING id""",
                (key, width // COLUMNS, height // ROWS),
            ).fetchone()[0]
        for pack in pack_rows:
            banner = None
            if pack.get("bg"):
                banner = publish(root, "banners", banner_path(source, pack["bg"]).read_bytes())
            pack_key = "legacy:" + pack["id"]
            pack_id = db.execute(
                """INSERT INTO pack(game_code,name,code,release_date,release_label,banner_key,metadata,legacy_key)
                   VALUES ('YUGIOH',%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT(legacy_key) DO UPDATE SET legacy_key=EXCLUDED.legacy_key RETURNING id""",
                (pack["name"], pack.get("code"), exact_date(pack.get("jp")), pack.get("kr") or pack.get("jp"),
                 banner, Jsonb({k: v for k, v in pack.items() if k != "cards"}), pack_key),
            ).fetchone()[0]
            for ordinal, card in enumerate(pack["cards"]):
                specs = {k: v for k, v in card.items()
                         if k not in ("n", "on", "c", "e", "r", "im", "il", "img")}
                inserted = db.execute(
                    """INSERT INTO card(game_code,pack_id,name,original_name,number,rarity,effect,
                                        release_date,specs,status,legacy_key)
                       VALUES ('YUGIOH',%s,%s,%s,%s,%s,%s,%s,%s,'PUBLISHED',%s)
                       ON CONFLICT(legacy_key) DO NOTHING RETURNING id""",
                    (pack_id, card.get("n") or card["on"], card.get("on"), card.get("c") or None,
                     card.get("r"), card.get("e"), exact_date(card.get("pd") or pack.get("jp")),
                     Jsonb(specs), f"{pack_key}:{entry_key(card, ordinal)}"),
                ).fetchone()
                if not inserted:
                    continue
                for position, variant in enumerate(variants(card)):
                    sheet_id = col = row = None
                    if variant.get("im") is not None:
                        index, col, row = variant["im"]
                        sheet_id = sheet_ids[index]
                    db.execute(
                        """INSERT INTO card_variant(card_id,position,rarity,sheet_id,col_idx,row_idx)
                           VALUES (%s,%s,%s,%s,%s,%s)""",
                        (inserted[0], position, variant.get("r"), sheet_id, col, row),
                    )
    return stats
