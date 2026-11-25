"""Exercise the offline worker against migrated Postgres tables, without loading any model weights."""
import os
import threading
import unittest
import uuid
from pathlib import Path
from unittest.mock import Mock, patch

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

from tcg_worker import translation


class RecordingModel:
    def __init__(self, on_first_call=None):
        self.calls = []
        self.on_first_call = on_first_call

    def translate(self, text, source, target):
        self.calls.append((text, source, target))
        if len(self.calls) == 1 and self.on_first_call:
            self.on_first_call()
        return f"[{source}>{target}] {text}"


@unittest.skipUnless(os.environ.get("TCG_TEST_DSN"), "set TCG_TEST_DSN to a test PostgreSQL/PostGIS database")
class TranslationDatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dsn = os.environ["TCG_TEST_DSN"]
        cls.schema = "test_translation_" + uuid.uuid4().hex
        cls.db = psycopg.connect(cls.dsn, autocommit=True)
        cls.addClassCleanup(cls.db.close)
        schema = sql.Identifier(cls.schema)
        cls.db.execute(sql.SQL("CREATE SCHEMA {}").format(schema))
        cls.addClassCleanup(cls.db.execute, sql.SQL("DROP SCHEMA {} CASCADE").format(schema))
        cls.db.execute(sql.SQL("SET search_path TO {},public").format(schema))
        migrations = Path(__file__).resolve().parents[2] / "backend/src/main/resources/db/migration"
        for migration in sorted(migrations.glob("V*.sql"), key=lambda path: int(path.name[1:].split("__")[0])):
            if migration.name.startswith("V9__"):
                cls.db.execute("""
                    INSERT INTO feed_item(source_id,external_id,source_url,payload,status)
                    SELECT s.id,v.kind,'https://example.invalid',jsonb_build_object('kind',v.kind,'title','Earlier title'),'PENDING'
                    FROM feed_source s CROSS JOIN (VALUES ('NEWS'),('OTHER')) v(kind)
                    WHERE s.source_key='weiss-en'
                """)
            if migration.name.startswith("V12__"):
                archive = cls.db.execute("""
                    INSERT INTO feed_item(source_id,external_id,source_url,payload,status)
                    SELECT id,'old-us','https://example.invalid',
                           '{"kind":"NEWS","title":"Stored title"}','PUBLISHED' FROM feed_source WHERE source_key='yugioh-en'
                    RETURNING id
                """).fetchone()[0]
                cls.db.execute("INSERT INTO feed_item_translation(item_id,lang,title) VALUES (%s,'ko','기존 제목')", (archive,))
            cls.db.execute(migration.read_text(encoding="utf-8"))
        cls.backfill = dict(cls.db.execute("SELECT external_id,translation_due_at IS NOT NULL FROM feed_item WHERE external_id<>'old-us'"))
        cls.archived = cls.db.execute("""
            SELECT s.enabled,s.policy_note IS NOT NULL,i.status,i.payload->>'title',t.title,i.translation_due_at
            FROM feed_item i JOIN feed_source s ON s.id=i.source_id JOIN feed_item_translation t ON t.item_id=i.id
            WHERE i.external_id='old-us'
        """).fetchone()
        cls.db.execute("DELETE FROM feed_item")

    def connection(self):
        return psycopg.connect(self.dsn, options=f"-c search_path={self.schema},public", autocommit=True)

    def add_item(self, key, title, summary=None, status="PUBLISHED"):
        source = self.db.execute("SELECT id FROM feed_source WHERE source_key=%s", (key,)).fetchone()[0]
        payload = {"kind": "NEWS", "title": title}
        if summary is not None:
            payload["summary"] = summary
        item = self.db.execute("""
            INSERT INTO feed_item(source_id,external_id,source_url,payload,status)
            VALUES (%s,%s,'https://example.invalid/item',%s,%s) RETURNING id
        """, (source, uuid.uuid4().hex, Jsonb(payload), status)).fetchone()[0]
        self.addCleanup(self.db.execute, "DELETE FROM feed_item WHERE id=%s", (item,))
        return item

    def rows(self, item):
        return {lang: (title, summary) for lang, title, summary in self.db.execute(
            "SELECT lang,title,summary FROM feed_item_translation WHERE item_id=%s", (item,))}

    def run_worker(self, factory):
        with patch.object(translation, "connect", side_effect=self.connection):
            translation.translate_pending(threading.Event(), model_factory=factory)

    def test_backfill_only_queues_existing_news(self):
        self.assertEqual(self.backfill, {"NEWS": True, "OTHER": False})

    def test_us_terms_pause_preserves_archive_and_excludes_it_from_translation(self):
        self.assertEqual(self.archived, (False, True, "PUBLISHED", "Stored title", "기존 제목", None))
        item = self.add_item("yugioh-en", "Stored title")
        self.assertEqual(translation.pending(self.db, 10), [])
        self.run_worker(Mock(side_effect=AssertionError("Archive must not invoke translation")))
        self.assertEqual(self.rows(item), {})

    def test_original_plus_translated_titles_and_summaries_preserve_moderation_and_skip_repeats(self):
        sources = [("weiss-en", "English announcement", "Details in English", "en", "PENDING"),
                   ("pokemon-jp", "新しいカードの発表", "発売日のお知らせ", "ja", "PUBLISHED"),
                   ("nivel-notice-kr", "새 카드 공개", "발매 일정 안내", "ko", "PUBLISHED")]
        items = [(self.add_item(key, title, summary, status), title, summary, language, status)
                 for key, title, summary, language, status in sources]
        rejected = self.add_item("weiss-en", "Rejected story", status="REJECTED")
        model = RecordingModel()
        factory = Mock(return_value=model)
        self.run_worker(factory)
        factory.assert_called_once()
        self.assertEqual(len(model.calls), 12)
        for item, title, summary, language, status in items:
            stored = self.db.execute(
                "SELECT original_language,status,payload,translation_due_at FROM feed_item WHERE id=%s", (item,)).fetchone()
            self.assertEqual(stored, (language, status, {"kind": "NEWS", "title": title, "summary": summary}, None))
            self.assertEqual(self.rows(item), {
                target: (f"[{language}>{target}] {title}", f"[{language}>{target}] {summary}")
                for target in translation.LANGUAGES if target != language})
        self.assertEqual(self.rows(rejected), {})
        # Even a requeued completed item must keep its translations without loading or calling the model.
        self.db.execute("UPDATE feed_item SET translation_due_at=now() WHERE id=%s", (items[0][0],))
        self.run_worker(factory)
        factory.assert_called_once()
        self.assertEqual(len(model.calls), 12)
        self.assertEqual(translation.pending(self.db, 10), [])

    def test_all_x_labels_are_deterministic_and_never_require_model_or_publish(self):
        labels = {"카드 공개": ("Card reveal", "カード公開"), "발매 소식": ("Release news", "発売情報"),
                  "대회 소식": ("Tournament news", "大会情報"), "새 게시물": ("New post", "新着投稿")}
        prefix = "@PokemonTCG · "
        items = [(self.add_item("PokemonTCG", prefix+ko, status="PENDING"), en, ja) for ko, (en, ja) in labels.items()]
        factory = Mock(side_effect=AssertionError("A deterministic label tried to load model weights"))
        self.run_worker(factory)
        for item, en, ja in items:
            self.assertEqual(self.rows(item), {"en": (prefix+en, None), "ja": (prefix+ja, None)})
            result = self.db.execute("SELECT original_language,status FROM feed_item WHERE id=%s", (item,)).fetchone()
            self.assertEqual(result, ("ko", "PENDING"))
        factory.assert_not_called()

    def test_edit_during_inference_invalidates_saved_rows_and_cannot_store_old_output(self):
        item = self.add_item("weiss-en", "Prior headline", "Old summary")
        self.db.execute("INSERT INTO feed_item_translation(item_id,lang,title,summary) VALUES (%s,'ko','이전 번역','이전 요약')", (item,))
        old = translation.pending(self.db, 1)[0]
        def replace_summary():
            with self.connection() as other:
                other.execute("UPDATE feed_item SET payload=payload || %s WHERE id=%s",
                              (Jsonb({"summary": "Revised summary"}), item))
        during_edit = RecordingModel(replace_summary)
        translation.translate_item(self.db, old, lambda: during_edit, threading.Event())
        self.assertEqual({target for _, _, target in during_edit.calls}, {"ja"})
        self.assertEqual(self.rows(item), {})
        queued = translation.pending(self.db, 1)[0]
        self.assertEqual((queued["id"], queued["summary"], queued["done"]), (item, "Revised summary", []))
        self.run_worker(lambda directory: RecordingModel())
        self.assertEqual(self.rows(item)["ko"][1], "[en>ko] Revised summary")

    def test_partial_translation_keeps_reviewed_title_and_fills_missing_summary(self):
        item = self.add_item("weiss-en", "Title", "Publisher excerpt")
        self.db.execute("INSERT INTO feed_item_translation(item_id,lang,title) VALUES (%s,'ko','검수한 제목')", (item,))
        self.run_worker(lambda directory: RecordingModel())
        self.assertEqual(self.rows(item)["ko"], ("검수한 제목", "[en>ko] Publisher excerpt"))

    def test_rejection_or_change_to_non_news_during_inference_cannot_write_translation(self):
        for change in ("rejection", "kind"):
            with self.subTest(change=change):
                item = self.add_item("weiss-en", "News subject", status="PENDING")
                candidate = translation.pending(self.db, 1)[0]
                def change_item():
                    with self.connection() as other:
                        if change == "rejection":
                            other.execute("UPDATE feed_item SET status='REJECTED' WHERE id=%s", (item,))
                        else:
                            other.execute("UPDATE feed_item SET payload=payload || %s WHERE id=%s",
                                          (Jsonb({"kind": "OTHER"}), item))
                model = RecordingModel(change_item)
                translation.translate_item(self.db, candidate, lambda: model, threading.Event())
                self.assertEqual(self.rows(item), {})
                self.assertEqual(translation.pending(self.db, 1), [])
