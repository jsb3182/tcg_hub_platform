-- Only numbered products have a language-independent identity. PROMO is an umbrella label.
CREATE FUNCTION onepiece_numbered_pack_key(code text) RETURNS text
LANGUAGE sql IMMUTABLE STRICT AS $$
    SELECT CASE WHEN code ~ '^(OP|ST|EB|PRB)-[0-9]{2}$' THEN
        'catalog:ONEPIECE:product:' || encode(sha256(convert_to('["'||code||'",""]','UTF8')),'hex')
    END
$$;

ALTER TABLE pack DROP CONSTRAINT pack_check;
ALTER TABLE pack ADD CONSTRAINT pack_catalog_alias CHECK (superseded_by IS NULL OR (
    superseded_by<>id AND legacy_key IS NOT NULL AND (
        (game_code='NIVEL' AND starts_with(legacy_key,'catalog:NIVEL:')) OR
        (game_code='ONEPIECE' AND onepiece_numbered_pack_key(code) IS NOT NULL
         AND legacy_key=onepiece_numbered_pack_key(code)))));

-- Existing automatic calendar entries can use either regional title.
CREATE TABLE onepiece_pack_label(
    pack_id bigint NOT NULL REFERENCES pack(id) ON DELETE CASCADE,
    name text NOT NULL,
    PRIMARY KEY(pack_id,name)
);
INSERT INTO onepiece_pack_label(pack_id,name)
SELECT id,name FROM pack WHERE game_code='ONEPIECE' AND onepiece_numbered_pack_key(code) IS NOT NULL
  AND legacy_key IN ('catalog:ONEPIECE:'||code,onepiece_numbered_pack_key(code));

LOCK TABLE card IN SHARE ROW EXCLUSIVE MODE;
CREATE TEMP TABLE op56_merge ON COMMIT DROP AS
SELECT original.id AS keep_id, duplicate.id AS old_id
FROM pack original JOIN pack duplicate ON duplicate.game_code=original.game_code
 AND duplicate.code=original.code AND duplicate.legacy_key=onepiece_numbered_pack_key(original.code)
WHERE original.game_code='ONEPIECE' AND original.legacy_key='catalog:ONEPIECE:'||original.code
  AND original.superseded_by IS NULL AND duplicate.superseded_by IS NULL
  AND (original.release_date IS NULL OR duplicate.release_date IS NULL OR original.release_date=duplicate.release_date)
  AND (original.release_label IS NULL OR duplicate.release_label IS NULL OR original.release_label=duplicate.release_label)
  AND (original.banner_key IS NULL OR duplicate.banner_key IS NULL OR original.banner_key=duplicate.banner_key)
  AND (original.metadata || duplicate.metadata) = (duplicate.metadata || original.metadata)
  AND NOT EXISTS(SELECT FROM card c WHERE c.pack_id IN (original.id,duplicate.id)
      AND starts_with(c.legacy_key,'catalog:ONEPIECE:')
      AND (c.number IS NULL OR c.number !~ '^((OP|ST|EB|PRB)[0-9]{2}-[0-9]{3}|P-[0-9]{3})(_[a-zA-Z0-9]+)?$'
           OR c.legacy_key IS DISTINCT FROM 'catalog:ONEPIECE:'||original.code||':'||c.number
           OR (c.specs ? 'productCode' AND c.specs->>'productCode' IS DISTINCT FROM original.code)));

INSERT INTO onepiece_pack_label(pack_id,name)
SELECT m.keep_id,d.name FROM op56_merge m JOIN pack d ON d.id=m.old_id
ON CONFLICT DO NOTHING;
UPDATE pack p SET release_date=coalesce(p.release_date,d.release_date),
    release_label=coalesce(p.release_label,d.release_label), banner_key=coalesce(p.banner_key,d.banner_key),
    metadata=p.metadata||d.metadata,edit_version=p.edit_version+1
FROM op56_merge m JOIN pack d ON d.id=m.old_id
WHERE p.id=m.keep_id AND (p.release_date,p.release_label,p.banner_key,p.metadata) IS DISTINCT FROM
    (coalesce(p.release_date,d.release_date),coalesce(p.release_label,d.release_label),coalesce(p.banner_key,d.banner_key),p.metadata||d.metadata);
UPDATE card c SET pack_id=m.keep_id,edit_version=c.edit_version+1 FROM op56_merge m WHERE c.pack_id=m.old_id;
UPDATE pack p SET superseded_by=m.keep_id,edit_version=p.edit_version+1 FROM op56_merge m WHERE p.id=m.old_id;

CREATE OR REPLACE VIEW catalog_pack_date AS
WITH matches AS (
    SELECT current_catalog_pack(e.selected_pack_id) AS pack_id,e.release_date
    FROM product_release e WHERE e.selected_pack_id IS NOT NULL
    UNION ALL
    SELECT min(p.id),min(e.release_date)
    FROM product_release e JOIN visible_catalog_pack p ON p.game_code=e.game_code
      AND (e.catalog_code IS NOT NULL OR e.catalog_name IS NOT NULL)
      AND (e.catalog_code IS NULL OR upper(p.code)=upper(e.catalog_code))
      AND (e.catalog_name IS NULL OR lower(p.name)=lower(e.catalog_name) OR (p.game_code='ONEPIECE' AND EXISTS
           (SELECT FROM onepiece_pack_label l WHERE l.pack_id=p.id AND lower(l.name)=lower(e.catalog_name))))
      AND CASE WHEN e.game_code='YUGIOH' AND starts_with(e.product_key,'na-premiere:')
               THEN p.metadata @> '{"wp":true,"sec":true}' ELSE starts_with(p.legacy_key,'catalog:') END
    WHERE NOT e.manual AND e.selected_pack_id IS NULL GROUP BY e.id HAVING count(*)=1
), announced AS (
    SELECT pack_id,min(release_date) AS release_date FROM matches GROUP BY pack_id
)
SELECT p.id AS pack_id,p.game_code,coalesce(p.release_date,a.release_date) AS release_date
FROM visible_catalog_pack p LEFT JOIN announced a ON a.pack_id=p.id
WHERE coalesce(p.release_date,a.release_date) IS NOT NULL;
