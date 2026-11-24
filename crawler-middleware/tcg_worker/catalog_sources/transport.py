"""Bounded local cache shared across restarts. Only adapter-defined source URLs are requested."""
import hashlib
import json
import os
import re
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class SameHostRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        old, new = urlsplit(req.full_url), urlsplit(newurl)
        if (new.hostname, new.scheme, new.port) != (old.hostname, old.scheme, old.port):
            raise ValueError("Unexpected cross-origin redirect from catalog source")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class CatalogHTTP:
    def __init__(self):
        spool = os.environ.get("SPOOL_ROOT")
        default = Path(spool).resolve().parent / "catalog-cache" if spool else Path.home() / ".cache/tcg-hub/catalog"
        self.root = Path(os.environ.get("CATALOG_CACHE_ROOT", default))
        self.root.mkdir(parents=True, exist_ok=True)
        self.opener = build_opener(SameHostRedirect)
        self.last_request = {}
        self.index_file = None
        self.index = {}

    @contextmanager
    def scan(self, game):
        # A single iterator owns this game's files until all archive streams have closed.
        with (self.root / f".{game}.lock").open("a+b") as lock:
            if os.name == "nt":
                import msvcrt
                if not lock.tell():
                    lock.write(b"0")
                    lock.flush()
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.index_file = self.root / f".{game}.revisions.json"
            if self.index_file.is_file():
                self.index = json.loads(self.index_file.read_text("utf-8"))
            try:
                yield
            finally:
                self.index_file = None

    def remember_revision(self, family, path):
        if not family or not self.index_file:
            return
        key = hashlib.sha256(family.encode()).hexdigest()
        previous = self.index.get(key, [])
        if previous == [path.name]:
            return
        # Keep any file an external Windows reader still has open and retry on the next scan.
        retained = []
        for name in previous:
            if name != path.name and re.fullmatch("[0-9a-f]{64}", name):
                try:
                    (self.root / name).unlink(missing_ok=True)
                except PermissionError:
                    retained.append(name)
        self.index[key] = [path.name, *retained]
        next_index = self.index_file.with_suffix(".tmp")
        next_index.write_text(json.dumps(self.index), encoding="utf-8")
        os.replace(next_index, self.index_file)

    def get(self, url, *, ttl=3600, size=8_000_000, post=None, delay=0.25, revision="", family=None):
        digest = hashlib.sha256(url.encode() + b"\0" + (post or b"") + revision.encode()).hexdigest()
        path = self.root / digest
        family = family or (url if revision else None)
        if path.exists() and time.time() - path.stat().st_mtime < ttl:
            self.remember_revision(family, path)
            return path
        host = urlsplit(url).hostname
        time.sleep(max(0, self.last_request.get(host, 0) + delay - time.monotonic()))
        self.last_request[host] = time.monotonic()
        request = Request(url, data=post, headers={"User-Agent": "TCGHub-Catalog/1.0"})
        # Propagate HTTPError (including Retry-After) intact to the source scheduler.
        with self.opener.open(request, timeout=90) as response:
            length = response.headers.get("Content-Length")
            if length and int(length) > size:
                raise ValueError(f"Catalog response from {host} exceeds size limit")
            fd, name = tempfile.mkstemp(dir=self.root, prefix=".fetch-")
            try:
                count = 0
                with os.fdopen(fd, "wb") as output:
                    while chunk := response.read(131072):
                        count += len(chunk)
                        if count > size:
                            raise ValueError(f"Catalog response from {host} exceeds size limit")
                        output.write(chunk)
                if not count or (length and count != int(length)):
                    raise ValueError(f"Incomplete catalog response from {host}")
                os.replace(name, path)
            finally:
                Path(name).unlink(missing_ok=True)
        self.remember_revision(family, path)
        return path
