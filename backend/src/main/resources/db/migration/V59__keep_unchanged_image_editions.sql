-- Preserve an existing local file grant when a catalog refresh adds another language.
-- Changed card identities and publication state still revoke every previous association.
CREATE OR REPLACE FUNCTION clear_catalog_art_card() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.status = 'PUBLISHED' AND
       (OLD.status, OLD.game_code, OLD.legacy_key, OLD.number, OLD.original_name, OLD.specs->>'konami_id')
       IS NOT DISTINCT FROM
       (NEW.status, NEW.game_code, NEW.legacy_key, NEW.number, NEW.original_name, NEW.specs->>'konami_id') THEN
        DELETE FROM catalog_art_card a USING catalog_art_file f
         WHERE a.card_id=OLD.id AND f.id=a.file_id AND NOT EXISTS (
               SELECT FROM (VALUES ('ko'),('en'),('ja')) edition(lang)
                WHERE f.source_url=OLD.specs->'images'->>edition.lang
                  AND f.source_url=NEW.specs->'images'->>edition.lang
         );
    ELSE
        DELETE FROM catalog_art_card WHERE card_id=OLD.id;
    END IF;
    RETURN NEW;
END $$;
