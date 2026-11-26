"""Regression for Play Termux where runsv's service PID is a PRoot tracer."""
import importlib.util
from pathlib import Path
import os
import shutil
import shlex
import signal
import subprocess
import sys
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

    def test_api_shuts_down_both_release_commands_under_the_supervised_tracer(self):
        launcher = source.with_name("ubuntu.sh").read_text(encoding="utf-8")
        entry = next(line for line in launcher.splitlines() if line.strip().startswith("exec java ") and
                     " --spring.config.import=" in line)
        current = shlex.split(entry.strip())[1:]
        previous = current[:-1]
        self.assertEqual(previous[-2:], ["-jar", "tcg-hub.jar"])
        for argv in (previous, current):
            with self.subTest(argv=argv):
                self.add(602, 601, ["/lib/ld-linux-aarch64.so.1", *argv])
                self.add(603, 601, [*previous, "--change-password=fixture"])
                self.add(401, 400, argv)
                def delivered(pid, sig):
                    self.assertEqual((pid, sig), (602, signal.SIGTERM))
                    (self.proc / str(pid) / "stat").unlink()

                with patch.object(stop.os, "uname", return_value=SimpleNamespace(release="4.14.117"), create=True), \
                     patch.object(stop.os, "kill", side_effect=delivered) as kill:
                    self.assertTrue(stop.terminate("api", self.pidfile, self.proc))
                kill.assert_called_once()
                self.assertTrue((self.proc / "401/stat").exists())
                self.assertTrue((self.proc / "603/stat").exists())

    def test_reject_other_jar_modes_and_application_arguments(self):
        jar = ["-jar", "tcg-hub.jar"]
        config = "--spring.config.import=optional:configtree:/etc/tcg-hub/web-config/"
        for args in (
            ["-jar", "another.jar", *jar], ["com.example.OtherMain", *jar],
            ["--module=example", *jar], [*jar, config, "--debug"],
            [*jar, config.replace("web-config", "other-config")],
            [*jar, "--provision-account=test", "--account-role=ROLE_USER"],
        ):
            with self.subTest(args=args):
                self.assertFalse(stop.guest_command("api", ["java", *args]))

    @unittest.skipUnless(sys.platform.startswith("linux") and all(shutil.which(x) for x in ("java","javac","jar")),
                         "requires Linux /proc and a JDK")
    def test_terminates_real_supervised_java_process(self):
        # The test JVM only announces readiness and sleeps. Start a separate tracer parent
        # so terminate() has exactly one supervised subtree to inspect in the real /proc.
        java = self.proc / "Waiter.java"
        java.write_text('public class Waiter { public static void main(String[] a) throws Exception { '
                        'System.out.println("READY"); Thread.sleep(60000); } }',encoding="utf-8")
        subprocess.run(["javac",java.name],cwd=self.proc,check=True)
        subprocess.run(["jar","cfe","tcg-hub.jar","Waiter","Waiter.class"],cwd=self.proc,check=True)
        proc_root = Path("/proc")
        for suffix in ([], ["--spring.config.import=optional:configtree:/etc/tcg-hub/web-config/"]):
            argv = ["java","-Xms256m","-Xmx1024m","-XX:ActiveProcessorCount=2","-jar","tcg-hub.jar",*suffix]
            with self.subTest(suffix=suffix), subprocess.Popen(
                [sys.executable,"-c","import subprocess,sys; sys.exit(subprocess.call(sys.argv[1:]))",*argv],
                stdout=subprocess.PIPE,cwd=self.proc,text=True,start_new_session=True,
            ) as tracer:
                try:
                    self.assertEqual(tracer.stdout.readline().strip(),"READY")
                    self.pidfile.write_text(str(tracer.pid))
                    self.assertTrue(stop.terminate("api", self.pidfile, proc_root))
                    self.assertNotEqual(tracer.wait(timeout=6),0)
                finally:
                    if tracer.poll() is None:
                        os.killpg(tracer.pid, signal.SIGKILL)


if __name__ == "__main__":
    unittest.main()
