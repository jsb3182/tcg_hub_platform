ALTER TABLE product_release ADD COLUMN publisher_category text
    CHECK (publisher_category IS NULL OR
           (game_code='ONEPIECE' AND publisher_category IN ('BOOSTERS','DECKS')));

CREATE OR REPLACE FUNCTION classify_product_release() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NOT NEW.manual THEN
        NEW.product_type := CASE NEW.publisher_category
            WHEN 'BOOSTERS' THEN 'BOOSTER'
            WHEN 'DECKS' THEN 'STARTER'
            ELSE release_kind(NEW.name)
        END;
    END IF;
    IF TG_OP='UPDATE' THEN NEW.version := OLD.version+1; END IF;
    RETURN NEW;
END $$;
