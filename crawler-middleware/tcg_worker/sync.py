"""A single scheduled worker; DB transactions cover a batch, never a provider request."""
import hashlib
import json
import logging
import re
import threading
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from itertools import islice
from urllib.error import HTTPError
from urllib.parse import urlsplit

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .catalog_news import collect_pack_dates, finish_yugioh_scan
from .catalog_sources.rift_editions import preserve_deferred
from .catalog_sources.onepiece import preserve_partial_korean
from .feeds import FetchError, backoff, fetch_feed
from .jobs import connect, process_once

LOG = logging.getLogger(__name__)
WORKER = "tcg-worker"
LOCK = 73401851
X_REQUEST_LOCK = 73401852


def claim(db, catalog):
    with db.cursor(row_factory=dict_row) as cur:
        return cur.execute("""
            WITH due AS (
              SELECT id FROM feed_source
               WHERE enabled AND state <> 'RUNNING' AND (provider='CATALOG')=%s
                 AND policy_note IS NULL
                 AND EXISTS (SELECT FROM collection_control WHERE crawler_enabled
                     AND (requested_at IS NOT NULL OR (scheduler_enabled AND (schedule_ready OR NOT spring_managed))))
                 AND coalesce(next_fetch_at,'-infinity') <= now()
                 AND coalesce(retry_after_at,'-infinity') <= now()
                 AND NOT EXISTS (SELECT 1 FROM feed_provider_cooldown p
                                  WHERE p.provider=feed_source.provider AND p.retry_after_at>now())
               ORDER BY requested_at NULLS LAST, next_fetch_at NULLS FIRST,
                        CASE WHEN provider='CATALOG' THEN 1 ELSE 0 END,id
               LIMIT 1 FOR UPDATE SKIP LOCKED
            )
            UPDATE feed_source s SET state='RUNNING',last_started_at=now(),requested_at=NULL,schedule_ready=false,
                                     last_seen=0,last_added=0
              FROM due WHERE s.id=due.id RETURNING s.*
        """, (catalog,)).fetchone()


def fetch_x_with_limits(db, key, cursor):
    # The worker and an operator's check-feed command can use the same X app simultaneously.
    if not db.execute("SELECT pg_try_advisory_lock(%s)", (X_REQUEST_LOCK,)).fetchone()[0]:
        raise FetchError("다른 X 조회가 진행 중입니다.", retry_after=15)
    try:
        remaining = db.execute("""
            SELECT ceil(extract(epoch FROM retry_after_at-now()))::bigint
            FROM feed_provider_cooldown WHERE provider='X' AND retry_after_at>now()
        """).fetchone()
        if remaining:
            raise FetchError("X 앱의 호출 제한 해제 시각을 기다립니다.", retry_after=remaining[0])

        def remember(seconds):
            # Both callers use autocommit so a crash while parsing the page preserves this deadline.
            db.execute("""
                INSERT INTO feed_provider_cooldown(provider,retry_after_at)
                VALUES ('X',now()+make_interval(secs=>%s))
                ON CONFLICT(provider) DO UPDATE SET retry_after_at=
                    greatest(feed_provider_cooldown.retry_after_at,EXCLUDED.retry_after_at)
            """, (seconds,))

        return fetch_feed("X", key, cursor, on_x_limit=remember)
    finally:
        db.execute("SELECT pg_advisory_unlock(%s)", (X_REQUEST_LOCK,))


def save_news(db, source, items):
    added = 0
    for item in items:
        payload = {"kind": "NEWS", "title": item.title}
        if item.summary:
            payload["summary"] = item.summary
        if item.published:
            payload["publishedAt"] = item.published.isoformat()
        row = db.execute("""
            INSERT INTO feed_item(source_id,external_id,source_url,payload,source_published_at,status)
              VALUES (%s,%s,%s,%s,%s,%s)
              ON CONFLICT(source_id,external_id) DO NOTHING RETURNING id
        """, (source["id"], item.external_id, item.url, Jsonb(payload), item.published,
              "PUBLISHED" if source["auto_publish"] else "PENDING")).fetchone()
        added += int(row is not None)
        if row and item.event and source.get("provider") == "X" and source.get("store_id"):
            category, starts = item.event
            db.execute("""
                INSERT INTO calendar_event(store_id,game_code,feed_item_id,source_event_key,title,category,starts_at,status)
                SELECT s.store_id,s.game_code,i.id,'store-notice',%s,%s,%s,i.status
                  FROM feed_item i JOIN feed_source s ON s.id=i.source_id
                 WHERE i.id=%s AND s.provider='X' AND s.store_id IS NOT NULL
                ON CONFLICT(feed_item_id,source_event_key) DO NOTHING
            """, ("매장 대회" if category == "TOURNAMENT" else "신상품 입고", category, starts, row[0]))
        if row is None and source["auto_publish"]:
            # A moderation decision applies to the exact text and link presented for review.
            # Only automatically published official news may take subsequent publisher edits.
            db.execute("""
                UPDATE feed_item SET payload=(payload-'summary') || %s,source_url=%s,
                       source_published_at=coalesce(%s,source_published_at)
                 WHERE source_id=%s AND external_id=%s AND payload->>'kind'='NEWS'
                   AND status='PUBLISHED' AND reviewer_id IS NULL
                   AND EXISTS (SELECT 1 FROM feed_source s WHERE s.id=feed_item.source_id
                               AND s.provider='OFFICIAL_NEWS' AND s.auto_publish)
                   AND (payload->>'title',payload->>'summary',source_url,source_published_at)
                       IS DISTINCT FROM (%s,%s,%s,coalesce(%s,source_published_at))
            """, (Jsonb(payload), item.url, item.published, source["id"], item.external_id,
                  item.title, item.summary, item.url, item.published))
    return added


def product_identity(code, name):
    title = " ".join(unicodedata.normalize("NFKC", name).split()).casefold()
    return code, re.sub(r"\s*([&:·「」])\s*", r"\1", title)


def existing_product_keys(db, game, prefix, records):
    # Earlier imports keyed packs by code. Keep each numeric ID for the product that row represents.
    codes = {card.get("pack_code") for card in records}
    rows = db.execute(
        """SELECT legacy_key,code,name FROM pack WHERE game_code=%s AND starts_with(legacy_key,%s)
           AND (game_code='NIVEL' OR NOT starts_with(legacy_key,%s))
           AND (code=ANY(%s::text[]) OR (code IS NULL AND %s)) ORDER BY id""",
        (game, prefix, prefix + "product:", [code for code in codes if code is not None], None in codes),
    )
    existing = {}
    for key, code, name in rows:
        existing.setdefault(product_identity(code, name), {}).setdefault(name, key)
    return existing


def save_cards(db, source, records):
    game = source["game_code"]
    prefix = f"catalog:{game}:"
    records = tuple(records)
    cards, packs = {}, {}
    existing = existing_product_keys(db, game, prefix, records)
    for card in records:
        external = str(card["external_id"])
        url = urlsplit(card["source_url"])
        if not external or not card["name"] or url.scheme not in ("http", "https") or not url.hostname or url.username:
            raise ValueError("Invalid catalog source record")
        key = prefix + external
        code = card.get("pack_code")
        raw_name = card.get("pack_name") or code
        pack_key = None
        if raw_name:
            # The regional catalog supplies one canonical product code; a newly verified
            # Korean label for that product must not allocate another numeric pack ID.
            identity = (code, "") if game == "ONEPIECE" and code else product_identity(code, raw_name)
            aliases = existing.get(identity)
            if aliases:
                pack_key = aliases.get(raw_name) or next(iter(aliases.values()))
            else:
                encoded = json.dumps(identity, ensure_ascii=False, separators=(",", ":")).encode()
                pack_key = prefix + "product:" + hashlib.sha256(encoded).hexdigest()
            name = " ".join(raw_name.split())
            if pack_key not in packs or name < packs[pack_key]["name"]:
                packs[pack_key] = {"key": pack_key, "code": code, "name": name}
        cards[key] = {**card, "key": key, "pack_key": pack_key}

    if game == "RIFTBOUND":
        preserve_deferred(db, cards)
    if game == "ONEPIECE":
        preserve_partial_korean(db, cards)
    if packs:
        db.execute("""
            INSERT INTO pack AS p(legacy_key,game_code,name,code)
              SELECT key,%s,name,code FROM jsonb_to_recordset(%s) AS v(key text,name text,code text)
            ON CONFLICT(legacy_key) DO UPDATE SET name=EXCLUDED.name
              WHERE p.name COLLATE "C" > EXCLUDED.name COLLATE "C"
        """, (game, Jsonb(list(packs.values()))))
    keys = list(cards)
    before = db.execute("SELECT count(*) FROM card WHERE legacy_key=ANY(%s)", (keys,)).fetchone()[0]
    db.execute("""
        INSERT INTO card AS c(legacy_key,game_code,pack_id,name,original_name,number,rarity,effect,
                              release_date,specs,source_url,source_id,status)
          SELECT v.key,%s,p.id,v.name,v.original_name,v.number,v.rarity,v.effect,v.release_date,
                 coalesce(v.specs,'{}'),v.source_url,%s,%s
            FROM jsonb_to_recordset(%s) AS v(key text,pack_key text,name text,original_name text,
                 number text,rarity text,effect text,release_date date,specs jsonb,source_url text)
            LEFT JOIN pack p ON p.legacy_key=v.pack_key
          ON CONFLICT(legacy_key) DO UPDATE SET pack_id=EXCLUDED.pack_id,name=EXCLUDED.name,
            original_name=EXCLUDED.original_name,number=EXCLUDED.number,rarity=EXCLUDED.rarity,
            effect=EXCLUDED.effect,release_date=EXCLUDED.release_date,specs=EXCLUDED.specs,
            source_url=EXCLUDED.source_url,source_id=EXCLUDED.source_id,edit_version=c.edit_version+1
          WHERE (c.pack_id,c.name,c.original_name,c.number,c.rarity,c.effect,c.release_date,
                 c.specs,c.source_url,c.source_id)
                IS DISTINCT FROM (EXCLUDED.pack_id,EXCLUDED.name,EXCLUDED.original_name,EXCLUDED.number,
                 EXCLUDED.rarity,EXCLUDED.effect,EXCLUDED.release_date,EXCLUDED.specs,EXCLUDED.source_url,EXCLUDED.source_id)
    """, (game, source["id"], "PUBLISHED" if source["auto_publish"] else "PENDING", Jsonb(list(cards.values()))))
    db.execute("""
        INSERT INTO card_variant AS v(card_id,position,rarity)
          SELECT id,0,rarity FROM card WHERE legacy_key=ANY(%s)
          ON CONFLICT(card_id,position) DO UPDATE SET rarity=EXCLUDED.rarity
            WHERE v.rarity IS DISTINCT FROM EXCLUDED.rarity
    """, (keys,))
    return len(keys) - before


class Interrupted(Exception):
    pass


def interrupted(db, source_id, stop):
    if stop.is_set():
        raise Interrupted()
    if not db.execute("SELECT enabled FROM feed_source WHERE id=%s", (source_id,)).fetchone()[0]:
        raise Interrupted()


def sync_source(source, stop):
    with connect() as db:
        db.autocommit = True
        sid = source["id"]
        try:
            cursor = json.loads(source["cursor_value"] or "{}")
            more, floor = False, 0
            page = None
            schedule = None
            calendar = None
            editions = None
            if source["provider"] == "CATALOG":
                from .catalog_sources import iter_catalog
                total = 0
                releases = {} if source["source_key"] == "YUGIOH" and "news" not in cursor else None
                if source["source_key"] == "YUGIOH" and source["game_code"] == "YUGIOH":
                    from .legacy_editions import LegacyEditions
                    editions = LegacyEditions.from_database(db, sid)
                records = iter(iter_catalog(source["game_code"], legacy_editions=editions))
                while True:
                    interrupted(db, sid, stop)
                    batch = list(islice(records, 10 if source["game_code"] == "NIVEL" else 200))
                    if not batch:
                        break
                    if releases is not None:
                        collect_pack_dates(releases, batch)
                    with db.transaction():
                        interrupted(db, sid, stop)
                        added = save_cards(db, source, batch)
                        db.execute("UPDATE feed_source SET last_seen=last_seen+%s,last_added=last_added+%s WHERE id=%s",
                                   (len(batch), added, sid))
                    total += len(batch)
                if total == 0:
                    raise FetchError("카드 목록이 비어 있습니다. 기존 카드 자료를 유지합니다.")
                previous=cursor
                cursor = {"count": total}
                if source["source_key"]=="YUGIOH":
                    from .catalog_art import queue_yugioh_art
                    cursor["artAfter"]=queue_yugioh_art(db,sid,previous.get("artAfter",0),stop)
            elif source["provider"] == "RELEASE_CALENDAR":
                from .release_calendar import fetch
                calendar = fetch(source["game_code"])
            elif source["provider"] == "STORE_SCHEDULE":
                from .store_schedules import fetch
                schedule = fetch(source["source_key"], cursor)
                cursor, more = schedule.cursor, schedule.more
            else:
                if source["provider"] == "X":
                    page = fetch_x_with_limits(db, source["source_key"], cursor)
                else:
                    page = fetch_feed(source["provider"], source["source_key"], cursor)
                cursor, more, floor = page.cursor, page.more, page.retry_after
            with db.transaction():
                interrupted(db, sid, stop)
                if calendar is not None:
                    from .release_calendar import save
                    added = save(db, calendar)
                    db.execute("UPDATE feed_source SET last_seen=%s,last_added=%s WHERE id=%s", (len(calendar), added, sid))
                if schedule is not None:
                    if schedule.deferred:
                        db.execute("""
                            UPDATE feed_source SET state='ERROR',last_finished_at=now(),last_error_at=now(),
                                last_error=%s,failure_count=failure_count+1,cursor_value=%s,
                                next_fetch_at=now()+make_interval(secs=>CASE WHEN requested_at IS NOT NULL
                                    THEN 0 WHEN %s THEN 60 ELSE interval_seconds END)
                                WHERE id=%s
                            """, (f"공식 행사 {schedule.notice}: {schedule.deferred}"[:300],
                                  json.dumps(cursor),more,sid))
                        return
                    from .store_schedules import save
                    seen, added = save(db, sid, schedule)
                    db.execute("UPDATE feed_source SET last_seen=%s,last_added=%s WHERE id=%s", (seen, added, sid))
                if source["provider"] == "CATALOG" and source["source_key"] == "YUGIOH":
                    if editions is not None:
                        editions.reconcile(db)
                        if editions.limit_checks:
                            from .yugioh_limits import save_checks
                            save_checks(db, editions.limit_checks)
                    cursor["news"] = finish_yugioh_scan(db, sid, releases)
                if page is not None:
                    added = save_news(db, source, page.items)
                    db.execute("UPDATE feed_source SET last_seen=%s,last_added=%s WHERE id=%s",
                               (len(page.items), added, sid))
                db.execute("""
                    UPDATE feed_source SET state='OK',last_finished_at=now(),last_success_at=now(),
                      last_error=NULL,failure_count=0,retry_after_at=CASE WHEN %s > 0 THEN now()+make_interval(secs=>%s) END,cursor_value=%s,
                      next_fetch_at=CASE WHEN requested_at IS NOT NULL THEN now() ELSE
                        now()+make_interval(secs => CASE WHEN %s THEN 60 ELSE interval_seconds END) END
                    WHERE id=%s
                """, (floor, floor, json.dumps(cursor), more, sid))
        except Interrupted:
            db.execute("UPDATE feed_source SET state='IDLE',last_finished_at=now(),next_fetch_at=now() WHERE id=%s", (sid,))
        except Exception as error:
            # Upstream exceptions may contain an authenticated URL or a full failed SQL statement.
            if isinstance(error, HTTPError):
                code = error.code
                delay = max(backoff(error.headers), 60 if code == 429 else 0)
                error.close()
                error = FetchError(f"HTTP {code} · 카드 제공자에서 요청을 거부했습니다.",
                                   blocked=code in (401, 402, 403), retry_after=delay)
            safe = str(error) if isinstance(error, FetchError) else f"{type(error).__name__} · 제공자 데이터 또는 연결 상태를 확인하세요."
            if isinstance(error, KeyError) and error.args and re.fullmatch(r"[a-zA-Z0-9_]{1,64}", str(error.args[0])):
                safe = f"제공자 응답에 {error.args[0]} 필드가 없습니다."
            blocked = isinstance(error, FetchError) and error.blocked
            floor = getattr(error, "retry_after", 0)
            failures = min(source["failure_count"], 8)
            delay = max(floor, min(21600, 60 * 2**failures), 21600 if blocked else 0)
            db.execute("""
                UPDATE feed_source SET state=%s,last_finished_at=now(),last_error_at=now(),last_error=%s,
                  failure_count=failure_count+1,retry_after_at=CASE WHEN %s > 0 THEN now()+make_interval(secs=>%s) END,
                  next_fetch_at=now()+make_interval(secs=>%s) WHERE id=%s
            """, ("BLOCKED" if blocked else "ERROR", safe[:300], floor, floor, delay, sid))
            LOG.warning("source %s/%s: %s", source["provider"], source["source_key"], safe)


def run(db, media, spool, stop, interval):
    db.autocommit = True
    if not db.execute("SELECT pg_try_advisory_lock(%s)", (LOCK,)).fetchone()[0]:
        raise RuntimeError("다른 수집 워커가 실행 중입니다.")
    from .release_calendar import seed_calendar
    with db.transaction():
        seed_calendar(db)
    db.execute("""
        INSERT INTO worker_heartbeat(id,started_at,seen_at) VALUES (%s,now(),now())
          ON CONFLICT(id) DO UPDATE SET started_at=now(),seen_at=now()
    """, (WORKER,))
    db.execute("""
        UPDATE feed_source SET state='IDLE',next_fetch_at=now()
          WHERE state='RUNNING'
    """)
    cancel = threading.Event()
    from .translation import model_directory, translate_pending
    next_translation_check = 0
    translating = None
    # Independent lanes keep slow imports and local inference out of the heartbeat loop.
    active = {}
    with ThreadPoolExecutor(max_workers=3, thread_name_prefix="tcg-sync") as pool:
        try:
            while not stop.is_set():
                restart = db.execute("UPDATE worker_heartbeat SET seen_at=now() WHERE id=%s RETURNING restart_requested_at",
                                     (WORKER,)).fetchone()[0]
                if restart:
                    cancel.set()
                    if any(not task.done() for task in active.values()) or (translating and not translating.done()):
                        stop.wait(1)
                        continue
                    db.execute("""
                        UPDATE worker_heartbeat SET restart_requested_at=NULL,restart_count=restart_count+1
                          WHERE id=%s
                    """, (WORKER,))
                    break
                for catalog in (False, True):
                    if catalog in active and active[catalog].done():
                        active.pop(catalog).result()
                    if catalog not in active:
                        source = claim(db, catalog)
                        if source:
                            active[catalog] = pool.submit(sync_source, source, cancel)
                if translating is not None and translating.done():
                    translating.result()
                    translating = None
                if translating is None and time.monotonic() >= next_translation_check:
                    next_translation_check = time.monotonic() + 30
                    if (model_directory() / "model.bin").is_file() and db.execute("""
                            SELECT EXISTS (SELECT 1 FROM feed_item i JOIN feed_source s ON s.id=i.source_id
                                           WHERE i.translation_due_at<=now() AND i.status <> 'REJECTED'
                                             AND s.policy_note IS NULL)
                            """).fetchone()[0]:
                        translating = pool.submit(translate_pending, cancel)
                media_count = process_once(db, media, spool)
                stop.wait(0.2 if media_count else min(interval, 3 if active else 10))
        finally:
            cancel.set()
