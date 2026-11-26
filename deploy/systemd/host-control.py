"""One fixed API-unit action on a socket already accepted by systemd."""
import socket
import struct
import subprocess


def handle(peer, api_uid, schedule):
    peer.settimeout(3)
    _, uid, _ = struct.unpack("3i", peer.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
    if uid != api_uid:
        peer.sendall(b"ERR\n")
        return
    with peer.makefile("rb") as reader:
        action = {b"restart\n": "restart", b"shutdown\n": "stop"}.get(reader.readline(16))
        if not action or not schedule(action):
            peer.sendall(b"ERR\n")
            return
        peer.sendall(b"OK\n")


def schedule(action):
    # Queue on the manager so that Spring can finish its HTTP 202 response.
    args = ["/usr/bin/systemd-run", "--quiet", "--collect", "--unit=tcg-hub-lifecycle",
            "--on-active=2s", "--timer-property=RemainAfterElapse=no",
            "/usr/bin/systemctl", "--no-block", action, "tcg-hub-api.service"]
    return subprocess.run(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                          timeout=4, check=False).returncode == 0


if __name__ == "__main__":
    import pwd
    with socket.socket(fileno=0) as peer:
        handle(peer, pwd.getpwnam("tcg-api").pw_uid, schedule)
