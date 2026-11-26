"""Existing-account decisions at the private terminal; no real accounts or factor secrets."""
import importlib.util
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location("enrollment", Path(__file__).resolve().parents[1] / "deploy/enroll-totp.py")
enrollment = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {"psycopg": Mock()}):
    spec.loader.exec_module(enrollment)


class AdminSetupTest(unittest.TestCase):
    def run_setup(self, record, choice, result=0):
        db, change, tty = Mock(), Mock(return_value=Mock(returncode=result)), io.StringIO()
        db.execute.return_value.fetchone.return_value = record
        read = Mock(side_effect=[" QA@EXAMPLE.TEST ", choice])
        with patch.object(enrollment, "enroll") as enroll:
            error = None
            try:
                enrollment.setup(db, tty, read, change)
            except enrollment.EnrollmentError as ex:
                error = str(ex)
        sql, args = db.execute.call_args.args
        self.assertIn("a.enabled AND a.role = 'ROLE_ADMIN'", sql)
        self.assertEqual(args, ("qa@example.test",))
        return change, enroll, error

    def test_only_existing_admin_may_continue(self):
        change, enroll, error = self.run_setup(None, "1")
        self.assertIsNotNone(error); change.assert_not_called(); enroll.assert_not_called()

    def test_password_failure_stops_enrollment(self):
        change, enroll, error = self.run_setup((1, None), "1", 1)
        self.assertIsNotNone(error); enroll.assert_not_called()
        change.assert_called_once_with(["/bin/bash", "/opt/tcg-hub/current/deploy/ubuntu.sh", "password", "qa@example.test"], check=False)

    def test_enroll_only_and_preserve_existing_factor(self):
        change, enroll, error = self.run_setup((1, None), "2")
        change.assert_not_called(); self.assertIsNone(error)
        self.assertEqual(enroll.call_args.args[1:3], ("qa@example.test", False))
        change, enroll, error = self.run_setup((1, "opaque-fingerprint"), "1")
        change.assert_called_once(); enroll.assert_not_called(); self.assertIsNone(error)
