"""Publish complete sheets and rebuild the visible cells when an older sheet is withdrawn."""
import hashlib
import logging
import re
from pathlib import Path

from PIL import Image

from .media import COLUMNS, ROWS, LIMIT_PIXELS, encode_sheet, publish


def store_sheet(db, root, image, width, height):
    revision = ""
    while True:
        data = encode_sheet(image, revision=revision)
        key = "sheets/" + hashlib.sha256(data).hexdigest() + ".webp"
        row = db.execute("""
            INSERT INTO image_sheet(storage_key,cell_width,cell_height) VALUES (%s,%s,%s)
            ON CONFLICT(storage_key) DO UPDATE SET storage_key=EXCLUDED.storage_key
               WHERE NOT image_sheet.retired RETURNING id
        """, (key, width, height)).fetchone()
        if row:
            publish(root, "sheets", data)
            return row[0]
        # Identical pixels can legitimately be published again. Preserve the withdrawal of the old URL.
        revision = key


def _rebuild(db, root, sheet_id, key, width, height):
    if not re.fullmatch(r"sheets/[0-9a-f]{64}\.webp", key):
        raise ValueError("Invalid stored atlas key")
    # Metadata edits lock the card first, then any variants and sheets. Follow the same order.
    db.execute("""
        SELECT c.id FROM card c WHERE EXISTS (SELECT 1 FROM card_variant v WHERE v.card_id=c.id AND v.sheet_id=%s)
          ORDER BY c.id FOR SHARE OF c
    """, (sheet_id,)).fetchall()
    cells = db.execute("""
        SELECT v.id,v.col_idx,v.row_idx,c.status FROM card_variant v JOIN card c ON c.id=v.card_id
        WHERE v.sheet_id=%s ORDER BY v.id FOR UPDATE OF v
    """, (sheet_id,)).fetchall()
    path = root / key
    visible = [(variant, col, row) for variant, col, row, status in cells if status == "PUBLISHED"]
    if not visible:
        if not cells:
            path.unlink(missing_ok=True)
        db.execute("UPDATE image_sheet SET repack_at=NULL WHERE id=%s", (sheet_id,))
        return
    size = (width * COLUMNS, height * ROWS)
    if size[0] * size[1] > LIMIT_PIXELS:
        raise ValueError("Atlas exceeds the supported pixel count")
    with path.open("rb") as stream:
        if key != "sheets/" + hashlib.file_digest(stream, "sha256").hexdigest() + ".webp":
            raise ValueError("Atlas bytes differ from their storage key")
        stream.seek(0)
        with Image.open(stream, formats=["WEBP"]) as old:
            if old.size != size or old.n_frames != 1:
                raise ValueError("Unexpected atlas dimensions")
            clean = Image.new("RGB", size, (24, 24, 24))
            for col, row in {(col, row) for _, col, row in visible}:
                box = (col * width, row * height, (col + 1) * width, (row + 1) * height)
                clean.paste(old.crop(box), box)
            target = store_sheet(db, root, clean, width, height)
    visible_ids = [variant for variant, _, _ in visible]
    # Only these locked variants supplied pixels. A later replacement has its own digest.
    db.execute("""
        INSERT INTO verified_atlas_edition(storage_key,col_idx,row_idx,language)
        SELECT DISTINCT s.storage_key,v.col_idx,v.row_idx,e.language
        FROM card_variant v JOIN verified_atlas_edition e
          ON e.storage_key=%s AND e.col_idx=v.col_idx AND e.row_idx=v.row_idx
        JOIN image_sheet s ON s.id=%s
        WHERE v.id=ANY(%s)
        ON CONFLICT DO NOTHING
    """, (key, target, visible_ids))
    db.execute("UPDATE card_variant SET sheet_id=%s WHERE id=ANY(%s)",
               (target, visible_ids))
    # Keep a private card's source for a later republication. Unused files are deleted on the next committed pass.
    db.execute("UPDATE image_sheet SET repack_at=CASE WHEN %s THEN now() END WHERE id=%s",
               (len(visible) == len(cells), sheet_id))


def repack_one(db, root: Path):
    sheet = db.execute("""
        SELECT id,storage_key,cell_width,cell_height FROM image_sheet
        WHERE repack_at<=now() ORDER BY repack_at,id LIMIT 1
    """).fetchone()
    if not sheet:
        return 0
    try:
        with db.transaction():
            _rebuild(db, root, *sheet)
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        logging.warning("Could not rebuild atlas %s: %s", sheet[0], exc)
        db.execute("UPDATE image_sheet SET repack_at=now()+interval '1 hour' WHERE id=%s", (sheet[0],))
    return 1
