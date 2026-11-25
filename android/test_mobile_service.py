"""Linux integration test: real runit, installer, inotify and mailbox with a fixture tcgctl."""
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
import uuid

INSTALLER = Path(__file__).resolve().parents[1] / "deploy" / "install-mobile-control.sh"
LOCAL = "http://127.0.0.1:8080"


def script(path, body):
    path.write_text("#!/bin/sh\nset -eu\n" + body)
    path.chmod(0o700)


def wait(check, seconds=15):
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        if check():
            return
        time.sleep(0.05)
    raise AssertionError("Timed out waiting for fixture")


@unittest.skipUnless(sys.platform.startswith("linux") and shutil.which("runsvdir") and shutil.which("sv"),
                     "requires Linux and runit")
class MobileSupervisor(unittest.TestCase):
    def setUp(self):
        work = tempfile.TemporaryDirectory()
        self.addCleanup(work.cleanup)
        root = Path(work.name)
        self.prefix, self.home = root / "usr", root / "home"
        self.svroot = self.prefix / "var/service"
        self.box = self.home / "tcg-control"
        self.log = self.home / "calls"
        self.origin = self.home / "origin"
        self.home.mkdir()
        self.log.touch()
        self.origin.write_text(LOCAL)
        self.svroot.mkdir(parents=True)
        binaries = self.prefix / "bin"
        binaries.mkdir()
        for name, target in [("sh", "/bin/sh"), ("python", sys.executable), ("sv", shutil.which("sv"))]:
            (binaries / name).symlink_to(target)
        for name in ("db", "api", "worker", "tunnel"):
            svc = self.svroot / ("tcg-" + name)
            svc.mkdir()
            (svc / "down").touch()
            script(svc / "run", "exec sleep 600\n")
        script(binaries / "proot-distro", """
[ "$#" = 9 ] && [ "$1" = login ] && [ "$2" = ubuntu-tcg ] && [ "$3" = --isolated ] &&
[ "$4" = --user ] && [ "$5" = tcgtunnel ] && [ "$6" = -- ] && [ "$7" = /bin/bash ] && [ "$8" = -c ] || exit 1
cat "$HOME/origin"
""")
        script(binaries / "tcgctl", """
[ "$#" = 1 ] || exit 1
case "$1" in start-local|start|stop) ;; *) exit 2;; esac
echo "$1" >> "$HOME/calls"
for name in db api worker tunnel; do
  service="$PREFIX/var/service/tcg-$name"
  if [ "$1" = stop ] || { [ "$1" = start-local ] && [ "$name" = tunnel ]; }; then
    touch "$service/down"
    sv -w 5 stop "$service"
  else
    rm -f "$service/down"
    sv -w 5 start "$service"
  fi
done
""")
        self.env = dict(os.environ, PREFIX=str(self.prefix), HOME=str(self.home))
        self.install()
        self.daemon = None
        self.addCleanup(self.stop_runit)
        self.start_runit()

    def install(self):
        subprocess.run(["bash", str(INSTALLER)], env=self.env, check=True, timeout=25)

    def start_runit(self):
        self.daemon = subprocess.Popen(["runsvdir", str(self.svroot)], env=self.env, start_new_session=True,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        wait(lambda: (self.svroot / "tcg-mobile/supervise/ok").exists())

    def stop_runit(self):
        if self.daemon:
            os.killpg(self.daemon.pid, signal.SIGKILL)
            self.daemon.wait(timeout=5)
            self.daemon = None

    def submit(self, action, identifier=None):
        ident = identifier or uuid.uuid4().hex
        path = self.box / f"request-{int(time.time()*1000)}-{ident}-{action}"
        path.touch()
        output = self.box / f"reply-{ident}.json"
        wait(lambda: output.is_file() and not path.exists())
        return ident, json.loads(output.read_text())

    def test_run_restart_and_default_state(self):
        _, first = self.submit("status")
        self.assertEqual(first["services"], dict.fromkeys(["db", "api", "worker", "tunnel"], "down"))
        ident, on = self.submit("start-local")
        self.assertEqual(on["services"], dict(db="up", api="up", worker="up", tunnel="down"))
        self.submit("start-local", ident)
        self.assertEqual(self.log.read_text().splitlines(), ["start-local"])
        self.assertEqual(self.submit("start-public")[1]["result"], "profile-changed")
        public = "https://cards.example.org"
        self.origin.write_text(public)
        self.assertEqual(self.submit("start-public")[1]["services"]["tunnel"], "up")
        self.assertEqual(self.submit("stop")[1]["services"], first["services"])
        self.install()  # Existing live service receives the upgraded bridge.
        self.stop_runit()
        self.start_runit()  # Simulate supervisor restart with prior down markers on disk.
        self.assertEqual(self.submit("status")[1]["services"], first["services"])
        self.assertEqual(self.submit("start-public")[1]["origin"], public)
        self.assertEqual(self.log.read_text().splitlines(), ["start-local", "start", "stop", "start"])


if __name__ == "__main__":
    unittest.main()
