import importlib.util
import json
import subprocess
import tempfile
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import Mock, patch

src = Path(__file__).resolve().parents[1] / "deploy" / "mobile-control.py"
spec = importlib.util.spec_from_file_location("mobile_control", src)
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


class MobileControl(unittest.TestCase):
    def test_start_requires_matching_profile(self):
        for origin, action, command in [
            (bridge.LOCAL, "start-local", "start-local"), ("https://cards.example.org", "start-public", "start"),
            ("", "start-public", None), ("", "start-local", None),
            (bridge.LOCAL, "start-public", None), ("https://cards.example.org", "start-local", None)
        ]:
            with self.subTest(origin=origin, action=action), patch.object(bridge, "profile", return_value=origin), \
                    patch.object(bridge, "snapshot", return_value={}), patch.object(subprocess, "run") as run:
                run.return_value.returncode = 0
                result = bridge.execute(action)
                if command:
                    self.assertEqual(run.call_args.args[0], [str(bridge.PREFIX / "bin/tcgctl"), command])
                    self.assertEqual(result["result"], "ok")
                else:
                    run.assert_not_called()
                    self.assertEqual(result["result"], "profile-changed")

    def test_status_stop_and_failures(self):
        with patch.object(bridge, "profile", side_effect=OSError()), patch.object(bridge, "snapshot", return_value={}), \
                patch.object(subprocess, "run") as run:
            self.assertEqual(bridge.execute("status"), {"result": "ok"})
            run.assert_not_called()
            run.return_value.returncode = 1
            self.assertEqual(bridge.execute("stop"), {"result": "command-failed"})
            self.assertEqual(run.call_args.args[0][-1], "stop")

    def test_mailbox_consumes_only_fresh_allowlisted_requests(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(bridge, "MAILBOX", Path(folder)), \
                patch.object(bridge, "execute", return_value={"result": "ok"}) as execute:
            now = int(time.time() * 1000)
            valid, stale = uuid.uuid4().hex, uuid.uuid4().hex
            for name in [f"request-{now}-{valid}-status", f"request-{now-100_000}-{stale}-start-public",
                         f"request-{now}-{uuid.uuid4().hex}-shell", "anything-else"]:
                (Path(folder) / name).touch()
            bridge.drain()
            (Path(folder) / f"request-{now}-{valid}-status").touch()
            bridge.drain()
            execute.assert_called_once_with("status")
            for ident, result in [(valid, "ok"), (stale, "expired")]:
                self.assertEqual(json.loads((Path(folder)/f"reply-{ident}.json").read_text()), {"result": result})

    def test_interrupted_claim_is_not_replayed(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(bridge, "MAILBOX", Path(folder)), \
                patch.object(bridge, "execute") as run:
            ident = uuid.uuid4().hex
            (Path(folder) / (".active-" + ident)).touch()
            (Path(folder) / f"request-{int(time.time()*1000)}-{ident}-start-public").touch()
            bridge.recover_interrupted()
            bridge.drain()
            run.assert_not_called()
            self.assertEqual(json.loads((Path(folder)/f"reply-{ident}.json").read_text()), {"result": "interrupted"})

    def test_only_fixed_readiness_and_service_paths(self):
        with patch.object(bridge.http.client, "HTTPConnection") as connect, patch.object(bridge.subprocess, "run") as run:
            run.side_effect = [Mock(stdout=s) for s in (b"run: db", b"down: api", b"run: worker", b"fail: tunnel")]
            connect.return_value.getresponse.return_value = Mock(status=200, read=lambda _: b'{"status":"UP"}')
            result = bridge.snapshot(bridge.LOCAL)
            self.assertTrue(result["ready"])
            connect.assert_called_once_with("127.0.0.1", 8080, timeout=2)
            connect.return_value.request.assert_called_once_with("GET", "/internal/ready")
            self.assertEqual(result["services"], dict(db="up", api="down", worker="up", tunnel="unknown"))


if __name__ == "__main__":
    unittest.main()
