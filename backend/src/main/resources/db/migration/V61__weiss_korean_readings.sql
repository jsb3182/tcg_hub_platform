-- A verified rule can be shown while its independently generated name is still pending.
ALTER TABLE card_korean_reading
    ADD COLUMN name_basis text CHECK (name_basis IN ('MACHINE_TRANSLATION','GLOSSARY_TRANSLATED','CURATED_TRANSLATION')),
    ADD COLUMN effect_basis text CHECK (effect_basis IN ('MACHINE_TRANSLATION','GLOSSARY_TRANSLATED','CURATED_TRANSLATION')),
    ADD COLUMN weiss_draft_due_at timestamptz;

CREATE INDEX card_korean_weiss_draft_due ON card_korean_reading(weiss_draft_due_at,card_id)
    WHERE weiss_draft_due_at IS NOT NULL;

CREATE OR REPLACE VIEW pending_korean_card_reading AS
    SELECT r.card_id,coalesce(r.due_at,r.weiss_draft_due_at) AS due_at
    FROM card_korean_reading r JOIN card c ON c.id=r.card_id
    WHERE (r.due_at IS NOT NULL OR r.weiss_draft_due_at IS NOT NULL)
      AND (advance_printing(c) OR (c.game_code='WEISS' AND c.specs->>'language'='en'
          AND c.legacy_key='catalog:WEISS:en:'||c.number AND c.status='PUBLISHED'));

-- Scope the vocabulary to English Weiss card titles/rules and a specific rendering version.
CREATE TABLE weiss_translation_memory (
    source_hash bytea PRIMARY KEY CHECK (octet_length(source_hash)=32),
    original text NOT NULL CHECK (length(original) BETWEEN 1 AND 8000),
    translated text CHECK (length(translated) BETWEEN 1 AND 8000)
);

-- V39 clears both texts when the source changes. Discard their field-specific credit and
-- pending second pass in that same update, including changes concurrent with PC imports.
CREATE FUNCTION reset_korean_reading_credit() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    NEW.name_basis := NULL;
    NEW.effect_basis := NULL;
    NEW.weiss_draft_due_at := NULL;
    RETURN NEW;
END
$$;
CREATE TRIGGER reset_source_reading_credit BEFORE UPDATE OF due_at ON card_korean_reading
    FOR EACH ROW WHEN (NEW.due_at IS NOT NULL AND NEW.name IS NULL AND NEW.effect IS NULL)
    EXECUTE FUNCTION reset_korean_reading_credit();

CREATE FUNCTION recheck_weiss_reading_number() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    UPDATE card_korean_reading SET name=NULL,effect=NULL,due_at=now() WHERE card_id=NEW.id;
    RETURN NULL;
END
$$;
CREATE TRIGGER changed_weiss_reading_number AFTER UPDATE OF number ON card
    FOR EACH ROW WHEN (NEW.game_code='WEISS' AND OLD.number IS DISTINCT FROM NEW.number)
    EXECUTE FUNCTION recheck_weiss_reading_number();
