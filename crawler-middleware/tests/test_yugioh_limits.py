import hashlib
import os
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from urllib.error import HTTPError
from unittest.mock import Mock

from tcg_worker.yugioh_limits import BASE, FILES, check_files, save_checks


class Checks(unittest.TestCase):
    def test_cache_observation_uses_source_mtime_and_preserves_retry_after(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache = root / "raw"
            cache.write_bytes(b"snapshot")
            os.utime(cache, (1704067200, 1704067200))
            http = Mock(root=root)
            http.get.side_effect = [cache, HTTPError(BASE+FILES["TCG"], 429, "limited", {"Retry-After":"3600"}, None)]
            data = check_files(http)
            self.assertEqual(data["OCG"], (hashlib.sha256(b"snapshot").hexdigest(), date(2024,1,1)))
            self.assertIsNone(data["TCG"])
            self.assertEqual(http.get.call_count, 2)
            self.assertEqual(check_files(http), {"OCG":None, "TCG":None})
            self.assertEqual(http.get.call_count, 2)


@unittest.skipUnless(os.environ.get("TCG_TEST_DSN"), "Requires isolated PostgreSQL")
class SavedChecks(unittest.TestCase):
    def test_revised_upstream_cannot_be_declared_current_unavailable_retains_limits(self):
        from psycopg import connect
        with connect(os.environ["TCG_TEST_DSN"]) as db, db.transaction(force_rollback=True):
            snapshot = db.execute("SELECT file_sha256,effective_on FROM yugioh_limit_list WHERE region='TCG'").fetchone()
            before = db.execute("SELECT konami_id,max_copies FROM yugioh_card_limit WHERE region='TCG' ORDER BY 1").fetchall()
            today = db.execute("SELECT current_date").fetchone()[0]
            start = today - timedelta(days=1)
            db.execute("UPDATE yugioh_limit_list SET verified_on=%s WHERE region='TCG'", (start,))
            def read():
                return db.execute("SELECT verified_on,evidence_status FROM yugioh_limit_list WHERE region='TCG'").fetchone()
            save_checks(db, {"TCG": ("a"*64,today)})
            self.assertEqual(read(), (start,"CHANGED"))
            save_checks(db, {"TCG": None})
            self.assertEqual(read(), (start,"UNAVAILABLE"))
            save_checks(db, {"TCG": (snapshot[0],start-timedelta(days=1))})
            self.assertEqual(read(), (start,"UNAVAILABLE"))
            save_checks(db, {"TCG": (snapshot[0],today)})
            self.assertEqual(read(), (today,"VERIFIED"))
            self.assertEqual(db.execute("SELECT konami_id,max_copies FROM yugioh_card_limit WHERE region='TCG' ORDER BY 1").fetchall(), before)
            self.assertEqual(db.execute("SELECT effective_on FROM yugioh_limit_list WHERE region='TCG'").fetchone()[0],snapshot[1])
