from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import zlib

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
import verify_namuwiki_printings as probe


def row(*values):
    return "<tr>" + "".join(f"<td>{value}</td>" for value in values) + "</tr>"


def seed(game, article, number, name):
    return {"game": game, "title": "검증 문서", "snapshotDate": probe.DATE,
            "snapshotUrl": probe.SNAPSHOT, "snapshotRow": 1,
            "articleSha256": hashlib.sha256(article.encode()).hexdigest(),
            "names": {"ko": name}, "match": {"number": number}, "printingNumber": number}


def populate(db, article):
    db.execute("create table meta(k text, v text)")
    db.executemany("insert into meta values(?,?)", probe.METADATA.items())
    db.execute("create table docs(id integer primary key, title text, md blob)")
    db.execute("insert into docs values(1,'검증 문서',?)", (zlib.compress(article.encode()),))
    db.commit()


class PrintingVerificationTests(unittest.TestCase):
    def test_onepiece_only_matches_the_current_card_block(self):
        header = row("라이프", "파워", "카드 번호")
        first = row("한글판 명칭", "첫 카드") + header + row("4", "5000", "OP01-001")
        second = row("한글판 명칭", "둘째 카드") + header + row("5", "4000", "OP01-002")
        for separator in ("", "</table><table>"):
            doc = "<table>" + first + separator + second + "</table>"
            with closing(sqlite3.connect(":memory:")) as db:
                populate(db, doc)
                good = seed("ONEPIECE", doc, "OP01-002", "둘째 카드")
                self.assertEqual(probe.verify(db, [good]), 1)
                with self.assertRaisesRegex(ValueError, "same card entry"):
                    probe.verify(db, [seed("ONEPIECE", doc, "OP01-002", "첫 카드")])

    def test_nivel_only_matches_adjacent_identity_in_one_table_row(self):
        doc = ("<table>" + row("제한 내용", "카드넘버", "카드명", "종류")
               + row("신규", "BT01-001", "첫 카드", "스킬") + row("BT01-002", "둘째 카드", "스킬")
               + "</table><table>" + row("BT01-003", "첫 카드") + "</table>")
        with closing(sqlite3.connect(":memory:")) as db:
            populate(db, doc)
            self.assertEqual(probe.verify(db, [seed("NIVEL", doc, "BT01-002", "둘째 카드")]), 1)
            for number in ("BT01-002", "BT01-003"):
                with self.assertRaisesRegex(ValueError, "same card entry"):
                    probe.verify(db, [seed("NIVEL", doc, number, "첫 카드")])

    def test_pinned_metadata_document_identity_and_effective_read_only_cli(self):
        doc = "<table>" + row("카드넘버", "카드명") + row("BT01-001", "첫 카드") + "</table>"
        good = seed("NIVEL", doc, "BT01-001", "첫 카드")
        with tempfile.TemporaryDirectory() as directory:
            dbfile = Path(directory) / "read only #archive.sqlite"
            with closing(sqlite3.connect(dbfile)) as db:
                populate(db, doc)
                for field, bad in (("title", "잘못된 문서"), ("snapshotDate", "2021-03-01"),
                                   ("snapshotUrl", "https://example.org/alternate"), ("snapshotRow", 2),
                                   ("articleSha256", "0" * 64), ("printingNumber", "BT01-002")):
                    with self.subTest(field=field), self.assertRaises(ValueError):
                        probe.verify(db, [{**good, field: bad}])
            before = dbfile.read_bytes()
            manifest = Path(directory) / "seed.json"
            manifest.write_text(json.dumps([good]), encoding="utf-8")
            command = [sys.executable, "-B", str(TOOLS / "verify_namuwiki_printings.py"),
                       str(dbfile), "--seed", str(manifest)]
            run = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn("Verified 1", run.stdout)
            self.assertEqual(before, dbfile.read_bytes())
            with closing(sqlite3.connect(dbfile)) as db:
                db.execute("update meta set v='2025' where k='generated_at_iso'")
                with self.assertRaisesRegex(ValueError, "metadata"):
                    probe.verify(db, [good])
