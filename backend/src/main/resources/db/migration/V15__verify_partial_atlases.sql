-- A raw source atlas can include stale pixels in positions without a current visible reference.
CREATE FUNCTION atlas_has_all_public_cells(target bigint) RETURNS boolean
LANGUAGE sql STABLE AS $$
    SELECT count(DISTINCT (v.col_idx, v.row_idx)) = 12
    FROM card_variant v JOIN card c ON c.id = v.card_id
    WHERE v.sheet_id = target AND c.status = 'PUBLISHED'
$$;

UPDATE image_sheet s SET retired = true, repack_at = now()
WHERE (NOT s.retired AND NOT atlas_has_all_public_cells(s.id))
   OR (s.retired AND s.repack_at IS NULL AND EXISTS (
        SELECT 1 FROM card_variant v JOIN card c ON c.id = v.card_id
        WHERE v.sheet_id = s.id AND c.status = 'PUBLISHED'));

-- A later import can attach a new public variant to a previously drained source atlas.
CREATE FUNCTION queue_retired_variant_target() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    UPDATE image_sheet SET repack_at = now() WHERE id = NEW.sheet_id AND retired;
    RETURN NULL;
END
$$;
CREATE TRIGGER queue_retired_variant_insert AFTER INSERT ON card_variant
    FOR EACH ROW WHEN (NEW.sheet_id IS NOT NULL) EXECUTE FUNCTION queue_retired_variant_target();
CREATE TRIGGER queue_retired_variant_move AFTER UPDATE OF sheet_id, col_idx, row_idx ON card_variant
    FOR EACH ROW WHEN (NEW.sheet_id IS NOT NULL AND
        (OLD.sheet_id, OLD.col_idx, OLD.row_idx) IS DISTINCT FROM (NEW.sheet_id, NEW.col_idx, NEW.row_idx))
    EXECUTE FUNCTION queue_retired_variant_target();
