"""Translate collected headlines and summaries locally. Originals remain in feed_item.payload."""
import logging
import os
import re
from pathlib import Path

from psycopg.rows import dict_row

from .jobs import connect

LOG = logging.getLogger(__name__)
LANGUAGES = ("ko", "en", "ja")
DEFAULT_MODEL = "/var/lib/tcg-hub/models/m2m100-418m-int8"
X_LABELS = {
    "카드 공개": {"en": "Card reveal", "ja": "カード公開"},
    "발매 소식": {"en": "Release news", "ja": "発売情報"},
    "대회 소식": {"en": "Tournament news", "ja": "大会情報"},
    "새 게시물": {"en": "New post", "ja": "新着投稿"},
}
SOURCE_LANGUAGES = {
    "weiss-en": "en", "riftbound-en": "en",
    "pokemon-jp": "ja", "nivel-kr": "ja", "nivel-notice-kr": "ko", "tcggame": "ko",
}
TRANSLATION_LOCK = 73401853


def model_directory():
    return Path(os.environ.get("TCG_TRANSLATION_MODEL") or DEFAULT_MODEL)


def original_language(source_key, title, summary=None):
    text = title + " " + (summary or "")
    if re.search(r"[가-힣]", text):
        return "ko"
    if re.search(r"[ぁ-ヿ]", text):
        return "ja"
    if re.search(r"[一-鿿]", text):
        return SOURCE_LANGUAGES.get(source_key)
    if re.search(r"[a-zA-Z]{2,}", text):
        return "en"
    return SOURCE_LANGUAGES.get(source_key)


class OfflineTranslator:
    def __init__(self, directory, threads=1):
        import ctranslate2
        import sentencepiece

        self.tokenizer = sentencepiece.SentencePieceProcessor(model_file=str(directory / "sentencepiece.bpe.model"))
        self.model = ctranslate2.Translator(str(directory), device="cpu", compute_type="int8",
                                            intra_threads=threads, inter_threads=1)

    def translate(self, text, source, target):
        if not text or not text.strip():
            return None
        # Split lengthy summaries at sentence boundaries; hard-split unusually long single sentences by tokens.
        parts = []
        for sentence in re.split(r"(?<=[.!?。！？])\s+|\n+", text.strip()):
            tokens = self.tokenizer.encode(sentence, out_type=str)
            parts.extend(tokens[i:i+160] for i in range(0, len(tokens), 160))
        inputs = [[f"__{source}__", *tokens, "</s>"] for tokens in parts]
        prefix = f"__{target}__"
        results = self.model.translate_batch(inputs, target_prefix=[[prefix] for _ in inputs],
                                             beam_size=3, max_batch_size=4, max_decoding_length=300,
                                             no_repeat_ngram_size=4)
        sentences = []
        for result in results:
            tokens = result.hypotheses[0]
            if tokens and tokens[0] == prefix:
                tokens = tokens[1:]
            rendered = self.tokenizer.decode(tokens).strip()
            if not rendered:
                raise ValueError("Empty translation")
            sentences.append(rendered)
        value = " ".join(sentences)
        if not value:
            raise ValueError("Empty translation")
        return value


def pending(db, limit):
    with db.cursor(row_factory=dict_row) as cur:
        return cur.execute("""
            SELECT i.id, s.provider, s.source_key, i.payload->>'title' AS title, i.payload->>'summary' AS summary,
                   i.original_language, ARRAY(SELECT lang FROM feed_item_translation t WHERE t.item_id=i.id
                        AND (nullif(trim(i.payload->>'summary'),'') IS NULL OR nullif(trim(t.summary),'') IS NOT NULL)) AS done
              FROM feed_item i JOIN feed_source s ON i.source_id=s.id
             WHERE i.translation_due_at <= now() AND i.status <> 'REJECTED' AND s.policy_note IS NULL
             ORDER BY i.translation_due_at,i.id LIMIT %s
        """, (limit,)).fetchall()


def translate_item(db, item, get_model, stop):
    source = item["original_language"] or original_language(item["source_key"], item["title"], item["summary"])
    if source is None:
        raise ValueError("Unknown original language")
    label = re.fullmatch(r"(@[A-Za-z0-9_]{1,15}) · (.+)", item["title"]) if item["provider"] == "X" else None
    converted = []
    for target in LANGUAGES:
        if stop.is_set():
            return
        if target == source or target in item["done"]:
            continue
        if label and label[2] in X_LABELS and source == "ko":
            title = f"{label[1]} · {X_LABELS[label[2]][target]}"
        else:
            title = get_model().translate(item["title"], source, target)
        summary = get_model().translate(item["summary"], source, target) if item["summary"] else None
        converted.append((item["id"], target, title, summary))
    with db.transaction():
        # Inference runs outside the transaction. A concurrent title edit has queued a new version.
        current = db.execute("""
            UPDATE feed_item SET original_language=%s,translation_due_at=NULL
             WHERE id=%s AND status <> 'REJECTED' AND translation_due_at IS NOT NULL
               AND EXISTS (SELECT 1 FROM feed_source s WHERE s.id=feed_item.source_id AND s.policy_note IS NULL)
               AND payload->>'kind'='NEWS' AND payload->>'title'=%s
               AND payload->>'summary' IS NOT DISTINCT FROM %s RETURNING id
        """, (source, item["id"], item["title"], item["summary"])).fetchone()
        if current and converted:
            with db.cursor() as cur:
                cur.executemany("""
                    INSERT INTO feed_item_translation(item_id,lang,title,summary) VALUES (%s,%s,%s,%s)
                    ON CONFLICT(item_id,lang) DO UPDATE SET summary=excluded.summary
                    WHERE nullif(trim(feed_item_translation.summary),'') IS NULL AND excluded.summary IS NOT NULL
                """, converted)


def translate_pending(stop, model_factory=OfflineTranslator):
    """One CPU lane drains the queue, then releases model memory until new posts arrive."""
    model = None
    def get_model():
        nonlocal model
        if model is None:
            model = model_factory(model_directory())
        return model

    with connect() as db:
        db.autocommit = True
        if not db.execute("SELECT pg_try_advisory_lock(%s)", (TRANSLATION_LOCK,)).fetchone()[0]:
            return
        while not stop.is_set():
            rows = pending(db, 8)
            if not rows:
                return
            for item in rows:
                if stop.is_set():
                    return
                try:
                    translate_item(db, item, get_model, stop)
                except (ValueError, RuntimeError, OSError, ImportError) as error:
                    LOG.warning("Translation deferred for post %d (%s)", item["id"], type(error).__name__)
                    db.execute("""
                        UPDATE feed_item SET translation_due_at=now()+interval '15 minutes'
                        WHERE id=%s AND translation_due_at<=now() AND payload->>'kind'='NEWS' AND payload->>'title'=%s
                          AND payload->>'summary' IS NOT DISTINCT FROM %s
                    """, (item["id"], item["title"], item["summary"]))
                    if model is None:
                        return
