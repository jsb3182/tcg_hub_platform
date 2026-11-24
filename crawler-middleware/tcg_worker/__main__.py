import argparse
import json
import os
import signal
import sys
import threading
from pathlib import Path

from .legacy import check, import_catalog


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
    probe = commands.add_parser("check-feed", help="Read one supported source without saving to the database")
    probe.add_argument("provider", choices=("OFFICIAL_NEWS", "X", "DCINSIDE"))
    probe.add_argument("key")
    args = parser.parse_args()
    if args.command == "check-legacy":
        print(json.dumps(check(args.source), ensure_ascii=False))
        return
    if args.command == "check-feed":
        from .feeds import FetchError, fetch_feed
        try:
            page = fetch_feed(args.provider, args.key, {})
        except FetchError as error:
            parser.exit(2, str(error) + "\n")
        print(json.dumps({"count": len(page.items), "latest": page.items[0].url if page.items else None},
                         ensure_ascii=False))
        return

    from .jobs import connect, enqueue, process_once

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
