"""Queue normalized source cells, publish immutable sheets and commit references together."""
import hashlib
import os
import uuid
from pathlib import Path

import psycopg
from PIL import Image

from .media import CELL, COLUMNS, ROWS, atomic_write, encode_sheet, normalized_png, place_cell, publish


def connect():
    return psycopg.connect(os.environ.get("DATABASE_URL", ""), connect_timeout=10)


def enqueue(db, spool: Path, variant_id: int, source: Path) -> int:
    data = normalized_png(source)
    digest = hashlib.sha256(data).hexdigest()
    with db.transaction():
        variant = db.execute(
            """SELECT c.status FROM card_variant v JOIN card c ON c.id=v.card_id WHERE v.id=%s
               FOR UPDATE OF v FOR SHARE OF c""",
            (variant_id,),
        ).fetchone()
        if not variant:
            raise ValueError(f"No card variant {variant_id}")
        if variant[0] != "PUBLISHED":
            raise ValueError("Only published cards can be added to public atlases")
        last = db.execute(
            "SELECT id,input_hash,status FROM media_job WHERE variant_id=%s ORDER BY id DESC LIMIT 1",
            (variant_id,),
        ).fetchone()
        if last and last[1] == digest and last[2] != "FAILED":
            return last[0]
        key = uuid.uuid4().hex + ".png"
        atomic_write(spool / key, data)
        return db.execute(
            "INSERT INTO media_job(variant_id,input_hash,spool_key) VALUES (%s,%s,%s) RETURNING id",
            (variant_id, digest, key),
        ).fetchone()[0]


def clean_done(db, spool: Path) -> None:
    # A restart after commit and before unlink picks up this same key again.
    with db.transaction():
        rows = db.execute(
            """SELECT id,spool_key FROM media_job WHERE status <> 'PENDING' AND spool_key IS NOT NULL
               ORDER BY id LIMIT 48 FOR UPDATE SKIP LOCKED"""
        ).fetchall()
        for job_id, key in rows:
            (spool / key).unlink(missing_ok=True)
            db.execute("UPDATE media_job SET spool_key=NULL WHERE id=%s", (job_id,))


def process_once(db, root: Path, spool: Path) -> int:
    clean_done(db, spool)
    with db.transaction():
        # Serialize atlas publication. The lock is released automatically on rollback or process death.
        if not db.execute("SELECT pg_try_advisory_xact_lock(83269431)").fetchone()[0]:
            return 0
        jobs = db.execute(
            """SELECT id,variant_id,spool_key,input_hash FROM media_job
               WHERE status='PENDING' ORDER BY id LIMIT 12 FOR UPDATE"""
        ).fetchall()
        if not jobs:
            return 0
        sheet = Image.new("RGB", (CELL[0] * COLUMNS, CELL[1] * ROWS), (24, 24, 24))
        placed = []
        for job_id, variant_id, key, digest in jobs:
            try:
                status = db.execute(
                    """SELECT c.status FROM card_variant v JOIN card c ON c.id=v.card_id
                       WHERE v.id=%s FOR SHARE OF c,v""",
                    (variant_id,),
                ).fetchone()
                if not status or status[0] != "PUBLISHED":
                    raise ValueError("Card is unpublished")
                with (spool / key).open("rb") as source:
                    # An RGB cell is smaller than 400 KiB uncompressed.
                    data = source.read(512 * 1024)
                    if hashlib.sha256(data).hexdigest() != digest or source.read(1):
                        raise ValueError("Spool integrity check failed")
                col, row = place_cell(sheet, data, len(placed))
                placed.append((job_id, variant_id, col, row))
            except (FileNotFoundError, ValueError, SyntaxError) as exc:
                db.execute(
                    "UPDATE media_job SET status='FAILED',error=%s,finished_at=now() WHERE id=%s",
                    (str(exc)[:300], job_id),
                )
        if placed:
            key = publish(root, "sheets", encode_sheet(sheet))
            sheet_id = db.execute(
                """INSERT INTO image_sheet(storage_key,cell_width,cell_height) VALUES (%s,%s,%s)
                   ON CONFLICT (storage_key) DO UPDATE SET storage_key=EXCLUDED.storage_key RETURNING id""",
                (key, *CELL),
            ).fetchone()[0]
            for job_id, variant_id, col, row in placed:
                db.execute(
                    "UPDATE card_variant SET sheet_id=%s,col_idx=%s,row_idx=%s WHERE id=%s",
                    (sheet_id, col, row, variant_id),
                )
                db.execute("UPDATE media_job SET status='DONE',finished_at=now() WHERE id=%s", (job_id,))
    clean_done(db, spool)
    return len(jobs)
