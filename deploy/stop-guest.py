"""Deliver runit's TERM to the application supervised through PRoot."""
import errno
import os
from pathlib import Path
import signal
import sys
import time


def process(proc, pid):
    try:
        # Fields 4 and 22 follow the parenthesized command, which may contain spaces.
        fields = (proc / str(pid) / "stat").read_bytes().rsplit(b") ", 1)[1].split()
        return int(fields[1]), int(fields[19])
    except (OSError, ValueError, IndexError):
        return None


def guest_command(service, argv):
    if not argv:
        return False
    name = os.path.basename(argv[0])
    if name.startswith("ld-linux-") or name in {"linker", "linker64"}:
        return guest_command(service, argv[1:])
    if name in {"bash", "sh"}:
        return argv[1:] == ["/opt/tcg-hub/current/deploy/ubuntu.sh", service]
    if service == "worker":
        return name == "python" and argv[1:] == ["-m", "tcg_worker", "run"]
    if service == "api":
        return name == "java" and argv[-2:] == ["-jar", "tcg-hub.jar"]
    return (name == "cloudflared" and argv[1:3] == ["tunnel", "--no-autoupdate"]
            and argv[-2:] == ["--token-file", "/etc/tcg-hub/tunnel.token"])


def descendants(proc, root):
    children = {}
    for directory in proc.iterdir():
        if directory.name.isdigit():
            pid = int(directory.name)
            info = process(proc, pid)
            if info:
                children.setdefault(info[0], []).append((pid, info[1]))
    pending = [(root, 0)]
    while pending:
        parent, depth = pending.pop()
        for pid, started in children.pop(parent, []):
            yield depth + 1, pid, started
            pending.append((pid, depth + 1))


def inside(proc, pid, root, root_identity):
    while pid > 1:
        info = process(proc, pid)
        if not info:
            return False
        if pid == root:
            return info == root_identity
        pid = info[0]
    return False


def command(proc, pid):
    try:
        return [os.fsdecode(a) for a in (proc / str(pid) / "cmdline").read_bytes().split(b"\0") if a]
    except OSError:
        return []


def wait_for_exit(proc, pid, started, service):
    # Keep runsv in control/t until the writer exits, including when its launcher exits first.
    # A client timeout must precede this deadline so tcgctl cannot proceed to pg_dump.
    deadline = time.monotonic() + (185 if service == "worker" else 65)
    while time.monotonic() < deadline:
        info = process(proc, pid)
        if not info or info[1] != started or not command(proc, pid):
            return
        time.sleep(0.2)
    print(f"tcg-{service}: target PID {pid} is still shutting down", file=sys.stderr)


def terminate(service, pidfile, proc=Path("/proc")):
    try:
        root = int(pidfile.read_text().strip())
    except (OSError, ValueError):
        return False
    if root <= 1 or not (root_identity := process(proc, root)):
        return False
    for _ in range(4):
        matches = [(depth, pid, started) for depth, pid, started in descendants(proc, root)
                   if guest_command(service, command(proc, pid))]
        # An entry script can still be waiting for readiness. Prefer its application child.
        for _, pid, started in sorted(matches, reverse=True):
            fd = None
            try:
                # A90's 4.14 kernel predates pidfds. Probe newer kernels only.
                kernel = tuple(int(part) for part in os.uname().release.split(".")[:2])
                if kernel >= (5, 3) and hasattr(os, "pidfd_open") and hasattr(signal, "pidfd_send_signal"):
                    try:
                        fd = os.pidfd_open(pid)
                    except OSError as error:
                        if error.errno not in (errno.ENOSYS, errno.EINVAL, errno.EPERM, errno.EACCES):
                            raise
                identity = process(proc, pid)
                if (not identity or identity[1] != started or not inside(proc, pid, root, root_identity)
                        or not guest_command(service, command(proc, pid))):
                    continue
                if fd is None:
                    os.kill(pid, signal.SIGTERM)
                else:
                    signal.pidfd_send_signal(fd, signal.SIGTERM)
                wait_for_exit(proc, pid, started, service)
                return True
            except ProcessLookupError:
                continue
            finally:
                if fd is not None:
                    os.close(fd)
        time.sleep(0.15)
    return False


if __name__ == "__main__":
    service = sys.argv[1] if len(sys.argv) == 2 else ""
    if service not in {"worker", "api", "tunnel"}:
        sys.exit(2)
    pidfile = Path(os.environ["PREFIX"]) / "var/service" / f"tcg-{service}" / "supervise/pid"
    # On a startup race or if the guest has exited, runsv performs its normal PID-scoped stop.
    sys.exit(0 if terminate(service, pidfile) else 1)
