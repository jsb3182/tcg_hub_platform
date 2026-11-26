"""Termux-private mailbox for the Android operator. Each request is a fixed action."""
import ctypes
import http.client
import json
import os
from pathlib import Path
import re
import select
import subprocess
import tempfile
import time


PREFIX = Path(os.environ.get("PREFIX", "/data/data/com.termux/files/usr"))
MAILBOX = Path.home() / "tcg-control"
SERVICES = ("db", "api", "worker", "tunnel")
REQUEST = re.compile(r"request-(\d{13})-([a-f0-9]{32})-(status|start-local|start-public|stop|admin-setup)")
REPLY = re.compile(r"reply-[a-f0-9]{32}\.json")
ACTIVE = re.compile(r"\.active-([a-f0-9]{32})")
LOCAL = "http://127.0.0.1:8080"
PROFILE = """
set -eu
config=/etc/tcg-hub
source /opt/tcg-hub/current/deploy/exposure.sh
source "$config/access.env"
if [[ $PUBLIC_ORIGIN == http://127.0.0.1:8080 && -z ${CF_TEAM_DOMAIN:-} && -z ${CF_AUDIENCE:-} ]]; then
  printf '%s' "$PUBLIC_ORIGIN"
elif valid_public_settings "$PUBLIC_ORIGIN" "${CF_TEAM_DOMAIN:-}" "${CF_AUDIENCE:-}"; then
  printf '%s' "$PUBLIC_ORIGIN"
else exit 1
fi
"""


def profile():
    result = subprocess.run([str(PREFIX / "bin/proot-distro"), "login", "ubuntu-tcg", "--isolated",
                             "--user", "tcgtunnel", "--", "/bin/bash", "-c", PROFILE],
                            capture_output=True, timeout=25, check=False)
    origin = result.stdout.decode("ascii", errors="replace")
    if result.returncode == 0 and (origin == LOCAL or re.fullmatch(r"https://[A-Za-z0-9.-]+", origin)):
        return origin
    return ""


def snapshot(origin):
    services = {}
    for service in SERVICES:
        result = subprocess.run([str(PREFIX / "bin/sv"), "status", str(PREFIX / "var/service" / ("tcg-" + service))],
                                capture_output=True, timeout=8, check=False)
        services[service] = ("up" if result.stdout.startswith(b"run:") else
                             "down" if result.stdout.startswith(b"down:") else "unknown")
    conn = http.client.HTTPConnection("127.0.0.1", 8080, timeout=2)
    try:
        conn.request("GET", "/internal/ready")
        response = conn.getresponse()
        ready = response.status == 200 and json.loads(response.read(1024)).get("status") == "UP"
    except (OSError, ValueError, http.client.HTTPException):
        ready = False
    finally:
        conn.close()
    return {"origin": origin, "services": services, "ready": ready,
            "adminSetup": origin == LOCAL and (PREFIX / "libexec/tcg-hub/admin-setup").is_file()}


def launch_admin_session():
    """One fixed interactive session. Only the TTY helper can acknowledge a launch."""
    import fcntl
    directory = PREFIX / "var/lib/tcg-hub/admin-session"
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    pending, started = directory / "pending", directory / "started"
    with (directory / "lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return "session-open"
    executable = PREFIX / "libexec/tcg-hub/admin-setup"
    launcher = PREFIX / "bin/am"
    if not executable.is_file() or not launcher.is_file():
        return "session-unavailable"
    uri = "com.termux.file:" + str(executable)
    # Boot-launched runit may not inherit the build variables of an interactive shell.
    play = (PREFIX / "libexec/tcg-hub/termux-play").exists() or os.environ.get("TERMUX_APK_RELEASE") == "GOOGLE_PLAY_STORE" or os.environ.get("TERMUX_VERSION", "").startswith("googleplay.")
    if play:
        args = ["start", "-a", "android.intent.action.RUN", "-n", "com.termux/.app.TermuxActivityInternal", "-d", uri]
    else:
        args = ["startservice", "-a", "com.termux.service_execute", "-n", "com.termux/.app.TermuxService", "-d", uri,
                "--es", "com.termux.execute.session_action", "0"]
    started.unlink(missing_ok=True)
    pending.touch()
    try:
        try:
            subprocess.run([str(launcher), *args], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=8, check=False)
        except (OSError, subprocess.SubprocessError):
            # A timed-out Android command may already have delivered its intent.
            pass
        for _ in range(36):
            if started.is_file():
                return "session-open"
            time.sleep(.25)
        return "session-unavailable"
    finally:
        pending.unlink(missing_ok=True)


def execute(action):
    try:
        origin = profile()
    except (OSError, subprocess.SubprocessError):
        origin = ""
    status = "ok"
    if action == "admin-setup":
        status = launch_admin_session() if origin == LOCAL else "profile-changed"
    elif action != "status":
        if action.startswith("start-") and (not origin or (action == "start-local") != (origin == LOCAL)):
            status = "profile-changed"
        else:
            command = {"start-local": "start-local", "start-public": "start", "stop": "stop"}[action]
            result = subprocess.run([str(PREFIX / "bin/tcgctl"), command], stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL, check=False)
            if result.returncode:
                status = "command-failed"
    return {"result": status, **snapshot(origin)}


def reply(identifier, payload):
    with tempfile.NamedTemporaryFile("w", dir=MAILBOX, prefix=".out-", delete=False) as stream:
        json.dump(payload, stream)
    os.replace(stream.name, MAILBOX / ("reply-" + identifier + ".json"))


def drain():
    for entry in sorted(MAILBOX.iterdir()):
        if entry.is_symlink() or not entry.is_file():
            continue
        match = REQUEST.fullmatch(entry.name)
        if not match:
            if REPLY.fullmatch(entry.name) and entry.stat().st_mtime < time.time() - 900:
                entry.unlink(missing_ok=True)
            continue
        submitted, identifier, action = match.groups()
        if (MAILBOX / ("reply-" + identifier + ".json")).is_file():
            entry.unlink()
            continue
        if not 0 <= time.time() - int(submitted) / 1000 <= 90:
            reply(identifier, {"result": "expired"})
            entry.unlink()
            continue
        # Keep a receipt while the command runs, including during a service restart.
        active = MAILBOX / (".active-" + identifier)
        entry.rename(active)
        try:
            answer = execute(action)
        except (OSError, subprocess.SubprocessError, ValueError):
            answer = {"result": "unavailable"}
        reply(identifier, answer)
        active.unlink()


def recover_interrupted():
    for entry in MAILBOX.glob(".active-*"):
        match = ACTIVE.fullmatch(entry.name)
        if match and entry.is_file() and not entry.is_symlink():
            ident = match[1]
            if not (MAILBOX / ("reply-" + ident + ".json")).exists():
                reply(ident, {"result": "interrupted"})
            entry.unlink()


def main():
    os.umask(0o077)
    MAILBOX.mkdir(mode=0o700, exist_ok=True)
    libc = ctypes.CDLL(None, use_errno=True)
    fd = libc.inotify_init1(os.O_CLOEXEC | os.O_NONBLOCK)
    if fd < 0 or libc.inotify_add_watch(fd, os.fsencode(MAILBOX), 0x100 | 0x80) < 0:  # CREATE, MOVED_TO
        raise OSError(ctypes.get_errno(), "Cannot watch Termux control folder")
    recover_interrupted()
    while True:
        drain()
        select.select([fd], [], [])
        os.read(fd, 65536)


if __name__ == "__main__":
    main()
