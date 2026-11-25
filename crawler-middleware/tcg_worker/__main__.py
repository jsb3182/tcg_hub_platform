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
