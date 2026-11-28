import argparse
import json
import os
import signal
import sys
import threading
from pathlib import Path

from .legacy import check, import_catalog


def check_catalogs(db):
    """Distinguish a completed source import from an empty or partially populated catalogue."""
    from .catalog_sources import CATALOG_GAMES
    rows = db.execute("""
        SELECT g.code, g.name, s.last_success_at,
               CASE WHEN NOT s.enabled THEN 'PAUSED' ELSE s.state END,
               count(c.id) AS imported
        FROM game g LEFT JOIN feed_source s
          ON s.provider='CATALOG' AND s.source_key=g.code AND s.game_code=g.code
        LEFT JOIN card c ON c.source_id=s.id AND c.game_code=g.code AND c.status='PUBLISHED'
        WHERE g.code=ANY(%s) GROUP BY g.code,g.name,s.id ORDER BY g.name
    """, (list(CATALOG_GAMES),)).fetchall()
    result = [{"game": code, "name": name, "state": state, "published": count,
               "last_success_at": success.isoformat() if success is not None else None}
              for code, name, success, state, count in rows]
    completed = {row["game"] for row in result if row["published"] and row["last_success_at"]}
    return {"initial_sync_complete": completed == CATALOG_GAMES, "catalogs": result}


def main():
    parser = argparse.ArgumentParser(description="TCG catalogue and atlas worker")
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("check-legacy", "import-legacy"):
        commands.add_parser(command).add_argument("source", type=Path)
    enqueue_command = commands.add_parser("enqueue")
    enqueue_command.add_argument("variant_id", type=int)
    enqueue_command.add_argument("image", type=Path)
    commands.add_parser("once")
    commands.add_parser("run")
    commands.add_parser("check-catalogs", help="Report completed imports and published cards for each game.")
    artwork = commands.add_parser("cache-card-art", help="Run one bounded batch of local card image downloads.")
    artwork.add_argument("--game", choices=("YUGIOH","POKEMON","WEISS","NIVEL","RIFTBOUND","ONEPIECE"))
    commands.add_parser("seed-ygo-kr-prints", help="Populate the empty Korean printing index from the existing local catalog cache.")
    weiss = commands.add_parser("seed-weiss-readings",help="Apply complete Korean rules for published English Weiss cards locally.")
    weiss.add_argument("--memory",type=Path,help="optional locally prepared and trusted .jsonl.gz model memory")
    weiss.add_argument("--sha256",help="expected digest of the supplied translation memory")
    weiss.add_argument("--draft-limit",type=int,default=0,help="also process this many pending cards using the local model")
    commands.add_parser("import-wiki-cards", help="Import verified card facts from a NamuWiki snapshot index.").add_argument("file", nargs="?", type=Path)
    commands.add_parser("seed-release-calendar", help="Import the bundled regional release announcements without a network request.")
    probe = commands.add_parser("check-feed", help="Read a source without storing posts. A configured X worker shares its rate limit.")
    probe.add_argument("provider", choices=("OFFICIAL_NEWS", "X", "DCINSIDE"))
    probe.add_argument("key")
    args = parser.parse_args()
    if args.command == "check-legacy":
        print(json.dumps(check(args.source), ensure_ascii=False))
        return
    if args.command == "check-feed":
        from .feeds import FetchError, fetch_feed
        try:
            if args.provider == "X" and os.getenv("X_BEARER_TOKEN") and any(
                    os.getenv(name) for name in ("DATABASE_URL", "PGDATABASE", "PGSERVICE", "PGHOST")):
                from .jobs import connect
                from .sync import fetch_x_with_limits
                with connect() as db:
                    db.autocommit = True
                    page = fetch_x_with_limits(db, args.key, {})
            else:
                page = fetch_feed(args.provider, args.key, {})
        except FetchError as error:
            parser.exit(2, str(error) + "\n")
        print(json.dumps({"count": len(page.items), "latest": page.items[0].url if page.items else None},
                         ensure_ascii=False))
        return

    from .jobs import connect, enqueue, process_once

    if args.command == "seed-weiss-readings":
        if bool(args.memory)!=bool(args.sha256) or not 0<=args.draft_limit<=20000:
            parser.error("--memory requires --sha256; --draft-limit must be 0–20000")
        from .card_readings import fill_readings, seed_curated_readings
        from .translation import model_directory, OfflineTranslator, TRANSLATION_LOCK
        from .weiss_readings import seed_all
        from .weiss_memory import import_memory
        stop=threading.Event()
        for sig in (signal.SIGINT,signal.SIGTERM):
            signal.signal(sig,lambda *_:stop.set())
        model=None
        def get_model():
            nonlocal model
            if model is None:
                model=OfflineTranslator(model_directory())
            return model
        with connect() as db:
            db.autocommit=True
            if not db.execute("SELECT pg_try_advisory_lock(%s)",(TRANSLATION_LOCK,)).fetchone()[0]:
                parser.exit(3,"The local translation lane is busy. Retry after its current batch.\n")
            added=import_memory(db,args.memory,args.sha256) if args.memory else 0
            with db.transaction():
                seed_curated_readings(db)
            report=seed_all(db,stop,use_memory=True)
            attempted=0
            while attempted<args.draft_limit and not stop.is_set():
                count=fill_readings(db,get_model,stop,min(6,args.draft_limit-attempted),weiss_only=True)
                if not count:
                    break
                attempted+=count
            print(json.dumps({**report,"memoryAdded":added,"draftRowsProcessed":attempted}))
        return

    if args.command == "cache-card-art":
        from .local_art import batch, GAMES
        with connect() as db:
            db.autocommit = True
            media = Path(os.environ.get("MEDIA_ROOT", "/var/lib/tcg-hub/media"))
            print(json.dumps({"cached": batch(db, media, threading.Event(), (args.game,) if args.game else GAMES)}))
        return

    if args.command == "import-wiki-cards":
        from .wiki_cards import import_wiki_cards
        with connect() as db:
            print(json.dumps(import_wiki_cards(db, args.file)))
        return

    if args.command == "seed-release-calendar":
        from .release_calendar import seed_calendar
        with connect() as db:
            print(json.dumps({"added":seed_calendar(db)}))
        return

    if args.command == "seed-ygo-kr-prints":
        from .catalog_sources.transport import CatalogHTTP
        from .catalog_sources.ygo_kr_print import seed_from_cache
        with connect() as db:
            print(json.dumps(seed_from_cache(db, CatalogHTTP())))
        return

    if args.command == "check-catalogs":
        with connect() as db:
            report = check_catalogs(db)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if not report["initial_sync_complete"]:
            parser.exit(3)
        return

    media = Path(os.environ.get("MEDIA_ROOT", "/var/lib/tcg-hub/media")).resolve()
    spool = Path(os.environ.get("SPOOL_ROOT", "/var/lib/tcg-hub/spool")).resolve()
    if spool.is_relative_to(media) or media.is_relative_to(spool):
        parser.error("MEDIA_ROOT and SPOOL_ROOT must be separate directories")
    with connect() as db:
        if args.command == "import-legacy":
            print(json.dumps(import_catalog(db, args.source, media), ensure_ascii=False))
        elif args.command == "enqueue":
            print(enqueue(db, spool, args.variant_id, args.image))
        elif args.command == "once":
            print(process_once(db, media, spool))
        else:
            interval = max(1, int(os.environ.get("WORKER_POLL_SECONDS", "15")))
            stop = threading.Event()
            for sig in (signal.SIGINT, signal.SIGTERM):
                signal.signal(sig, lambda *_: stop.set())
            from .sync import run
            run(db, media, spool, stop, interval)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
