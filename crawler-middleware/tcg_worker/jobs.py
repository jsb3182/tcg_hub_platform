"""Queue normalized source cells, publish immutable sheets and commit references together."""
import hashlib
import os
import re
import time
import uuid
from pathlib import Path

import psycopg
from PIL import Image

from .atlases import repack_one, store_sheet
from .media import CELL, COLUMNS, ROWS, atomic_write, normalized_png, place_cell


_last_spool_scan = 0.0
_spool_name = re.compile(r"(?:[0-9a-f]{32}\.png|\.tmp-[a-z0-9_]{8})")


def connect():
    return psycopg.connect(os.environ.get("DATABASE_URL", ""), connect_timeout=10)


def enqueue(db, spool: Path, variant_id: int, source: Path) -> int:
    data = normalized_png(source)
    digest = hashlib.sha256(data).hexdigest()
    with db.transaction():
        variant = db.execute(
            """SELECT c.status,v.sheet_id FROM card_variant v JOIN card c ON c.id=v.card_id WHERE v.id=%s
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
        if last and last[1] == digest and (last[2] == "PENDING" or (last[2] == "DONE" and variant[1] is not None)):
            return last[0]
        db.execute("SELECT pg_advisory_xact_lock_shared(83269432)")
        key = uuid.uuid4().hex + ".png"
        atomic_write(spool / key, data)
        return db.execute(
            "INSERT INTO media_job(variant_id,input_hash,spool_key) VALUES (%s,%s,%s) RETURNING id",
            (variant_id, digest, key),
        ).fetchone()[0]


def reclaim_orphans(db, spool: Path) -> None:
    """Recover private files left by a crash before commit or by a cascading row deletion."""
    if not spool.is_dir():
        return
    cutoff = time.time() - 3600
    with db.transaction():
        # Both producers hold the shared lock through commit when creating spool files.
        if not db.execute("SELECT pg_try_advisory_xact_lock(83269432)").fetchone()[0]:
            return
        for entry in spool.iterdir():
            if not _spool_name.fullmatch(entry.name) or entry.is_symlink() or not entry.is_file():
                continue
            try:
                if entry.stat().st_mtime < cutoff and not db.execute(
                    "SELECT 1 FROM media_job WHERE spool_key=%s", (entry.name,)
                ).fetchone():
                    entry.unlink(missing_ok=True)
            except FileNotFoundError:
                continue


def clean_done(db, spool: Path) -> None:
    global _last_spool_scan
    now = time.monotonic()
    if not _last_spool_scan or now - _last_spool_scan >= 3600:
        reclaim_orphans(db, spool)
        _last_spool_scan = now
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
        repacked = repack_one(db, root)
        jobs = db.execute(
            """SELECT id,variant_id,spool_key,input_hash FROM media_job
               WHERE status='PENDING' ORDER BY id LIMIT 12 FOR UPDATE"""
        ).fetchall()
        if not jobs:
            return repacked
        sheet = Image.new("RGB", (CELL[0] * COLUMNS, CELL[1] * ROWS), (24, 24, 24))
        placed = []
        for job_id, variant_id, key, digest in jobs:
            try:
                if db.execute("""SELECT EXISTS(SELECT 1 FROM media_job
                                  WHERE variant_id=%s AND id>%s AND status<>'FAILED')""",
                              (variant_id, job_id)).fetchone()[0]:
                    raise ValueError("Superseded by a newer image for this variant")
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
            sheet_id = store_sheet(db, root, sheet, *CELL)
            for job_id, variant_id, col, row in placed:
                db.execute(
                    "UPDATE card_variant SET sheet_id=%s,col_idx=%s,row_idx=%s WHERE id=%s",
                    (sheet_id, col, row, variant_id),
                )
                db.execute("UPDATE media_job SET status='DONE',finished_at=now() WHERE id=%s", (job_id,))
    clean_done(db, spool)
    return len(jobs)
