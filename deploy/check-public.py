"""Check the published TCG Hub routes over HTTPS as a visitor without cookies."""
import argparse
import http.client
import json
import sys
import time
from urllib.parse import urljoin, urlsplit


GAMES = {"NIVEL", "POKEMON", "RIFTBOUND", "WEISS", "YUGIOH"}


class RouteError(ValueError):
    pass


def check_routes(origin, team, fetch):
    def get(path):
        status, location, body = fetch(path)
        if status >= 500:
            raise ConnectionError(f"{path} returned HTTP {status}")
        return status, location, body

    status, _, body = get("/")
    if status != 200 or b'id="app"' not in body:
        raise RouteError(f"Public home page did not return the app (HTTP {status})")
    status, _, body = get("/api/v1/games")
    if status != 200:
        raise RouteError(f"Public catalog returned HTTP {status}, expected 200")
    try:
        games = json.loads(body)
        if not isinstance(games, list) or {g["code"] for g in games} != GAMES:
            raise ValueError()
    except (UnicodeError, ValueError, KeyError, TypeError) as exc:
        raise RouteError("Public catalog did not return the five supported games") from exc

    for path in ("/admin", "/api/v1/admin/operations"):
        status, location, _ = get(path)
        if status in (401, 403):
            continue
        target = urlsplit(urljoin(origin, location or ""))
        if (status in (301, 302, 303, 307, 308)
                and target.scheme == "https" and target.netloc.lower() in (urlsplit(origin).netloc.lower(), team.lower())
                and target.path.startswith("/cdn-cgi/access/login/")):
            continue
        raise RouteError(f"{path} returned HTTP {status}, expected denial or Cloudflare Access sign-in")

    status, _, _ = get("/internal/ready")
    if status not in (401, 403, 404):
        raise RouteError(f"/internal/ready returned HTTP {status}, expected denial")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("origin", help="Published HTTPS origin")
    parser.add_argument("team", help="Configured team.cloudflareaccess.com")
    args = parser.parse_args()
    origin = urlsplit(args.origin)
    if (origin.scheme != "https" or not origin.hostname or origin.netloc.lower() != origin.hostname
            or origin.path not in ("", "/") or origin.query or origin.fragment):
        parser.error("expected an HTTPS origin with a hostname")

    def fetch(path):
        conn = http.client.HTTPSConnection(origin.hostname, timeout=6)
        try:
            conn.request("GET", path, headers={"Cache-Control": "no-cache"})
            response = conn.getresponse()
            body = response.read(16384) if path in ("/", "/api/v1/games") and response.status == 200 else b""
            return response.status, response.getheader("Location"), body
        finally:
            conn.close()

    for attempt in range(3):
        try:
            check_routes(args.origin, args.team, fetch)
            print(f"Public catalog and anonymous route checks passed: {args.origin}")
            return 0
        except RouteError as exc:
            print(exc, file=sys.stderr)
            return 1
        except (OSError, http.client.HTTPException) as exc:
            if attempt == 2:
                print(f"Public HTTPS check failed: {exc}", file=sys.stderr)
                return 1
            time.sleep(2)


if __name__ == "__main__":
    sys.exit(main())
