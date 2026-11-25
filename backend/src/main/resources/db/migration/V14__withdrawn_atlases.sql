-- A shared sheet contains the pixels of every cell, including ones the current UI does not select.
ALTER TABLE image_sheet ADD COLUMN retired boolean NOT NULL DEFAULT false,
                        ADD COLUMN repack_at timestamptz;
CREATE INDEX image_sheet_repack ON image_sheet(repack_at,id) WHERE repack_at IS NOT NULL;

CREATE FUNCTION card_visibility_changed() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    UPDATE image_sheet s SET retired=true,repack_at=now()
      WHERE EXISTS (SELECT 1 FROM card_variant v WHERE v.card_id=NEW.id AND v.sheet_id=s.id);
    RETURN NULL;
END
$$;
CREATE TRIGGER repack_on_card_visibility AFTER UPDATE OF status ON card
    FOR EACH ROW WHEN ((OLD.status='PUBLISHED') <> (NEW.status='PUBLISHED'))
    EXECUTE FUNCTION card_visibility_changed();

CREATE FUNCTION retire_old_variant_sheet() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    UPDATE image_sheet SET retired=true,repack_at=now() WHERE id=OLD.sheet_id;
    RETURN NULL;
END
$$;
CREATE TRIGGER repack_on_variant_change AFTER UPDATE OF sheet_id,col_idx,row_idx ON card_variant
    FOR EACH ROW WHEN (OLD.sheet_id IS NOT NULL AND
        (OLD.sheet_id,OLD.col_idx,OLD.row_idx) IS DISTINCT FROM (NEW.sheet_id,NEW.col_idx,NEW.row_idx))
    EXECUTE FUNCTION retire_old_variant_sheet();
CREATE TRIGGER repack_on_variant_delete AFTER DELETE ON card_variant
    FOR EACH ROW WHEN (OLD.sheet_id IS NOT NULL) EXECUTE FUNCTION retire_old_variant_sheet();

UPDATE image_sheet s SET retired=true,repack_at=now()
 WHERE EXISTS (SELECT 1 FROM card_variant v JOIN card c ON c.id=v.card_id
                WHERE v.sheet_id=s.id AND c.status<>'PUBLISHED');
