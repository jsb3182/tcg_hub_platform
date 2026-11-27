ALTER TABLE catalog_art_file ADD COLUMN capture_hash bit(64);
CREATE INDEX catalog_art_capture ON catalog_art_file(game_code,id) WHERE capture_hash IS NOT NULL;
