-- Local translations are disposable reading aids. Original and operator-reviewed editions stay independent.
CREATE TABLE card_korean_reading (
    card_id bigint PRIMARY KEY REFERENCES card ON DELETE CASCADE,
    name text,
    effect text,
    due_at timestamptz
);
CREATE INDEX card_korean_reading_due ON card_korean_reading(due_at,card_id) WHERE due_at IS NOT NULL;

CREATE FUNCTION needs_korean_reading(c card) RETURNS boolean LANGUAGE sql IMMUTABLE AS $$
    SELECT c.status='PUBLISHED' AND starts_with(c.legacy_key,'catalog:'||c.game_code||':')
        AND c.specs->>'language' IN ('en','ja')
        AND (nullif(c.specs->'names'->>'ko','') IS NULL OR
             (nullif(c.effect,'') IS NOT NULL AND nullif(c.specs->'texts'->>'ko','') IS NULL))
$$;

CREATE FUNCTION queue_card_korean_reading() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP='UPDATE' AND (OLD.name,OLD.effect,OLD.specs->>'language',OLD.specs->'names'->>'ko',
                           OLD.specs->'texts'->>'ko',OLD.status,OLD.legacy_key,OLD.source_url)
        IS NOT DISTINCT FROM (NEW.name,NEW.effect,NEW.specs->>'language',NEW.specs->'names'->>'ko',
                              NEW.specs->'texts'->>'ko',NEW.status,NEW.legacy_key,NEW.source_url) THEN
        RETURN NULL;
    END IF;
    IF needs_korean_reading(NEW) THEN
        INSERT INTO card_korean_reading(card_id,due_at) VALUES(NEW.id,now())
        ON CONFLICT (card_id) DO UPDATE SET name=NULL,effect=NULL,due_at=now();
    ELSE
        DELETE FROM card_korean_reading WHERE card_id=NEW.id;
    END IF;
    RETURN NULL;
END $$;
CREATE TRIGGER queue_card_korean_reading AFTER INSERT OR UPDATE OF name,effect,specs,status,legacy_key,source_url ON card
FOR EACH ROW EXECUTE FUNCTION queue_card_korean_reading();
INSERT INTO card_korean_reading(card_id,due_at) SELECT c.id,now() FROM card c WHERE needs_korean_reading(c);
