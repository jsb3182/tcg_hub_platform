import importlib.util
import os
from pathlib import Path
import socket
import unittest
from unittest.mock import patch

path = Path(__file__).resolve().parents[1] / "deploy" / "systemd" / "host-control.py"
spec = importlib.util.spec_from_file_location("host_control", path)
control = importlib.util.module_from_spec(spec)
spec.loader.exec_module(control)


class LifecycleTest(unittest.TestCase):
    @unittest.skipUnless(hasattr(socket, "SO_PEERCRED"), "Linux kernel peer credentials")
    def test_bound_socket_actions_and_peer(self):
        for command, uid, accepted, reply in [
            (b"restart\n", os.getuid(), ["restart"], b"OK\n"),
            (b"shutdown\n", os.getuid(), ["stop"], b"OK\n"),
            (b"something-else\n", os.getuid(), [], b"ERR\n"),
            (b"restart\n", os.getuid()+1, [], b"ERR\n"),
        ]:
            app, worker = socket.socketpair()
            with self.subTest(command=command, uid=uid), app, worker:
                seen = []
                app.sendall(command)
                control.handle(worker, uid, lambda action: seen.append(action) is None)
                self.assertEqual(reply, app.recv(16))
                self.assertEqual(accepted, seen)

    def test_queue_is_fixed_and_does_not_execute_a_shell(self):
        with patch.object(control.subprocess, "run") as run:
            run.return_value.returncode = 0
            self.assertTrue(control.schedule("restart"))
            args, kwargs = run.call_args
            self.assertEqual(args[0][-3:], ["--no-block", "restart", "tcg-hub-api.service"])
            self.assertNotIn("shell", kwargs)
