ALTER TABLE feed_item
    ADD COLUMN original_language text CHECK (original_language IN ('ko','en','ja')),
    ADD COLUMN translation_due_at timestamptz;

CREATE TABLE feed_item_translation (
    item_id bigint NOT NULL REFERENCES feed_item(id) ON DELETE CASCADE,
    lang text NOT NULL CHECK (lang IN ('ko','en','ja')),
    title text NOT NULL CHECK (length(trim(title)) > 0),
    summary text,
    PRIMARY KEY (item_id,lang)
);

CREATE INDEX news_translation_due ON feed_item(translation_due_at,id)
    WHERE translation_due_at IS NOT NULL AND status <> 'REJECTED';

CREATE FUNCTION queue_news_translation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'UPDATE' THEN
        IF (OLD.payload->>'kind', OLD.payload->>'title', OLD.payload->>'summary')
           IS NOT DISTINCT FROM (NEW.payload->>'kind', NEW.payload->>'title', NEW.payload->>'summary') THEN
            RETURN NEW;
        END IF;
        DELETE FROM feed_item_translation WHERE item_id=NEW.id;
        NEW.original_language := NULL;
    END IF;
    NEW.translation_due_at := CASE WHEN NEW.payload->>'kind'='NEWS'
        AND length(trim(NEW.payload->>'title')) > 0 THEN now() END;
    RETURN NEW;
END $$;

CREATE TRIGGER feed_item_news_translation BEFORE INSERT OR UPDATE OF payload ON feed_item
    FOR EACH ROW EXECUTE FUNCTION queue_news_translation();

UPDATE feed_item SET translation_due_at=now()
WHERE payload->>'kind'='NEWS' AND length(trim(payload->>'title')) > 0;
