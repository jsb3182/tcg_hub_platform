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


class GiveawayTitleTests(unittest.TestCase):
    def test_preserves_product_edition_and_distinguishes_winners(self):
        cases = [
            ("【Giveaway】Booster Pack A:B -Two Worlds- Vol.3",
             "A:B -Two Worlds- Vol.3 부스터 팩 증정 이벤트", "ブースターパック「A:B -Two Worlds- Vol.3」プレゼントキャンペーン"),
            ("[Giveaway] Extra Booster 86 Collection Vol. 12 Winners",
             "86 Collection Vol. 12 엑스트라 부스터 증정 이벤트 당첨자 발표", "エクストラブースター「86 Collection Vol. 12」プレゼントキャンペーン 当選者発表"),
            ("【Giveaway】EXPO 2025", "EXPO 2025 증정 이벤트", "「EXPO 2025」プレゼントキャンペーン"),
            ("【Giveaway】Owl's Journey! Re:Edit Giveaway Winners",
             "Owl's Journey! Re:Edit 증정 이벤트 당첨자 발표", "「Owl's Journey! Re:Edit」プレゼントキャンペーン 当選者発表"),
            ("[Giveaway] Trial Deck and Booster Pack Star: Dawn",
             "Star: Dawn 트라이얼 덱 및 부스터 팩 증정 이벤트", "トライアルデッキ＆ブースターパック「Star: Dawn」プレゼントキャンペーン"),
        ]
        for title, ko, ja in cases:
            with self.subTest(title=title):
                self.assertEqual(translation.weiss_giveaway_titles(title), {"ko": ko, "ja": ja})
        for title in ("Update to Booster Pack A Vol.3", "【Giveaway】 Winners", "[Giveaway]Booster Pack",
                      "【Giveaway】Booster Pack A Vol.3 postponed", "【Giveaway】Booster Pack A Vol."):
            self.assertEqual(translation.weiss_giveaway_titles(title), {})


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

    def test_numbered_giveaway_new_item_recollection_and_restart(self):
        title = "【Giveaway】Premium Booster Example! Vol.12"
        item = self.add_item("weiss-en", title, "Draw on Friday", "PENDING")
        other = self.add_item("riftbound-en", title)
        model = RecordingModel()
        self.run_worker(lambda _: model)
        self.assertEqual(self.rows(item)["ko"], ("Example! Vol.12 프리미엄 부스터 증정 이벤트", "[en>ko] Draw on Friday"))
        self.assertEqual(self.rows(item)["ja"], ("プレミアムブースター「Example! Vol.12」プレゼントキャンペーン", "[en>ja] Draw on Friday"))
        self.assertEqual(self.rows(other)["ko"][0], f"[en>ko] {title}")
        self.db.execute("UPDATE feed_item SET payload=payload WHERE id=%s", (item,))
        self.run_worker(Mock(side_effect=AssertionError("Restart reprocessed an unchanged item")))
        revised = title + " Winners"
        self.db.execute("UPDATE feed_item SET payload=payload || %s WHERE id=%s", (Jsonb({"title": revised}), item))
        self.run_worker(lambda _: model)
        self.assertEqual(self.rows(item)["ko"][0], "Example! Vol.12 프리미엄 부스터 증정 이벤트 당첨자 발표")
        self.assertEqual(self.rows(item)["ja"][0], "プレミアムブースター「Example! Vol.12」プレゼントキャンペーン 当選者発表")
        self.assertEqual(self.db.execute("SELECT status,payload->>'title' FROM feed_item WHERE id=%s",
                                         (item,)).fetchone(), ("PENDING", revised))

    def test_v16_repairs_only_clipped_copy_without_touching_review_or_summaries(self):
        migration = (Path(__file__).resolve().parents[2] / "backend/src/main/resources/db/migration"
                     / "V16__repair_clipped_weiss_giveaway_volume.sql").read_text(encoding="utf-8")
        title = "[Giveaway] Extra Booster Star 86 Vol. 12 Winners"
        clipped = title.replace("Vol. 12", "Vol.")
        rows = [
            ("weiss-en", "PUBLISHED", clipped, "Star 86 Vol. 12 엑스트라 부스터 증정 이벤트 당첨자 발표"),
            ("weiss-en", "PENDING", clipped, "Star 86 Vol. 12 엑스트라 부스터 증정 이벤트 당첨자 발표"),
            ("weiss-en", "PUBLISHED", "별빛 86 12탄 추첨 당첨자", "별빛 86 12탄 추첨 당첨자"),
            ("weiss-en", "REJECTED", clipped, clipped),
            ("riftbound-en", "PUBLISHED", clipped, clipped),
        ]
        prepared = []
        for key, status, old, expected in rows:
            item = self.add_item(key, title, "Original excerpt", status)
            self.db.execute("UPDATE feed_item SET original_language='en',translation_due_at=NULL WHERE id=%s", (item,))
            self.db.execute("""INSERT INTO feed_item_translation VALUES
                (%s,'ko',%s,'검수한 요약'),(%s,'ja','確認済み','元の要約')""", (item, old, item))
            row = self.db.execute("SELECT to_jsonb(i) FROM feed_item i WHERE i.id=%s", (item,)).fetchone()
            prepared.append((item, expected, row))
        self.assertEqual(self.db.execute(migration).rowcount, 2)
        self.assertEqual(self.db.execute(migration).rowcount, 0)
        for item, expected, before in prepared:
            self.assertEqual(self.rows(item), {"ko": (expected, "검수한 요약"), "ja": ("確認済み", "元の要約")})
            self.assertEqual(self.db.execute("SELECT to_jsonb(i) FROM feed_item i WHERE i.id=%s",
                                             (item,)).fetchone(), before)

    def test_v17_changes_only_proven_model_titles_and_preserves_reviews_and_originals(self):
        migration = (Path(__file__).resolve().parents[2] / "backend/src/main/resources/db/migration"
                     / "V17__localize_weiss_giveaway_titles.sql").read_text(encoding="utf-8")
        edition = "【Giveaway】Booster Pack Rascal Does Not Dream Vol. 4"
        bad_ko = "【Giveaway】Booster Pack Rascal은 꿈을 꾸지 않는다 Vol. 4 개"
        winners = "【Giveaway】Girls Band Cry Giveaway Winners"
        prepared = []
        cases = [
            (edition, "weiss-en", "PUBLISHED", bad_ko, edition + "位", {"ko", "ja"}),
            (edition, "weiss-en", "PENDING", bad_ko, "確認したタイトル", {"ko"}),
            (winners, "weiss-en", "PUBLISHED", "검수한 당첨자 발표", "【Giveaway】Girls Band Cry Giveaway 優勝", {"ja"}),
            (edition, "riftbound-en", "PUBLISHED", bad_ko, edition + "位", set()),
            (edition, "weiss-en", "REJECTED", bad_ko, edition + "位", set()),
            (edition + " Winners", "weiss-en", "PUBLISHED", bad_ko, edition + "位", set()),
        ]
        for original, source, status, ko, ja, fixed in cases:
            item = self.add_item(source, original, "Publisher's excerpt", status)
            self.db.execute("UPDATE feed_item SET original_language='en',translation_due_at=NULL WHERE id=%s", (item,))
            self.db.execute("""INSERT INTO feed_item_translation VALUES
                (%s,'ko',%s,'검수된 요약'),(%s,'ja',%s,'確認済みの要約'),(%s,'en','original','original summary')""",
                            (item, ko, item, ja, item))
            expected = self.rows(item)
            for target in fixed:
                expected[target] = (translation.weiss_giveaway_titles(original)[target], expected[target][1])
            original_row = self.db.execute("SELECT to_jsonb(i) FROM feed_item i WHERE id=%s", (item,)).fetchone()
            prepared.append((item, expected, original_row))
        self.assertEqual(self.db.execute(migration).rowcount, 4)
        self.assertEqual(self.db.execute(migration).rowcount, 0)
        self.run_worker(Mock(side_effect=AssertionError("Migration must not enqueue unchanged originals")))
        for item, expected, original_row in prepared:
            self.assertEqual(self.rows(item), expected)
            self.assertEqual(self.db.execute("SELECT to_jsonb(i) FROM feed_item i WHERE id=%s", (item,)).fetchone(), original_row)

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
