"""Regression for Play Termux where runsv's service PID is a PRoot tracer."""
import importlib.util
from pathlib import Path
import signal
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


source = Path(__file__).resolve().parents[1] / "deploy" / "stop-guest.py"
spec = importlib.util.spec_from_file_location("guest_stop", source)
stop = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stop)
WORKER = ["/opt/tcg-hub/current/venv/bin/python", "-m", "tcg_worker", "run"]


class GuestStopTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.proc = Path(temp.name)
        self.pidfile = self.proc / "supervised-pid"
        self.pidfile.write_text("600")
        self.add(600, 500, ["proot"])
        self.add(601, 600, ["sh", "-c", "run worker"])
        self.add(602, 601, WORKER)
        self.add(401, 400, WORKER)

    def add(self, pid, parent, argv, start=None):
        path = self.proc / str(pid)
        path.mkdir(exist_ok=True)
        # All services in the real incident shared PGID 777. Field 22 identifies a process instance.
        fields = ["S", str(parent), "777", *(["0"] * 16), str(start or pid)]
        (path / "stat").write_text(f"{pid} (process name) " + " ".join(fields))
        (path / "cmdline").write_bytes(b"\0".join(arg.encode() for arg in argv))

    def test_target_worker_even_if_tracer_does_not_forward_signals(self):
        def delivered(pid, sig):
            self.assertEqual((pid, sig), (602, signal.SIGTERM))
            (self.proc / str(pid) / "stat").unlink()

        with patch.object(stop.os, "uname", return_value=SimpleNamespace(release="4.14.117"), create=True), \
             patch.object(stop.os, "kill", side_effect=delivered) as kill:
            self.assertTrue(stop.terminate("worker", self.pidfile, self.proc))
        kill.assert_called_once()
        self.assertTrue((self.proc / "401/stat").exists())

    def test_skip_reparented_or_reused_pid(self):
        for new_parent, new_start in [(400, 602), (601, 800)]:
            self.add(602, 601, WORKER)
            def race(proc, root):
                self.add(602, new_parent, WORKER, new_start)
                yield 2, 602, 602

            with patch.object(stop, "descendants", side_effect=race), \
                 patch.object(stop.time, "sleep"), \
                 patch.object(stop.os, "uname", return_value=SimpleNamespace(release="4.14.117"), create=True), \
                 patch.object(stop.os, "kill") as kill:
                self.assertFalse(stop.terminate("worker", self.pidfile, self.proc))
                kill.assert_not_called()

    def test_service_commands(self):
        self.assertTrue(stop.guest_command("api", ["java", "-Xmx1024m", "-jar", "tcg-hub.jar"]))
        self.assertFalse(stop.guest_command("api", ["java", "-jar", "tcg-hub.jar", "--provision-account=a"]))
        self.assertTrue(stop.guest_command("tunnel", ["cloudflared", "tunnel", "--no-autoupdate", "run",
                                                     "--token-file", "/etc/tcg-hub/tunnel.token"]))
        self.assertFalse(stop.guest_command("worker", ["proot", *WORKER]))
        self.assertTrue(stop.guest_command("worker", ["bash", "/opt/tcg-hub/current/deploy/ubuntu.sh", "worker"]))


if __name__ == "__main__":
    unittest.main()
