-- V56 left numbered products separate when their OPTCG DON!! cards had no collector number.
-- Only reconcile a still-visible original/hash pair with verified DON!! and compatible edits.
LOCK TABLE pack,card IN SHARE ROW EXCLUSIVE MODE;
CREATE TEMP TABLE op57_merge ON COMMIT DROP AS
SELECT original.id AS keep_id, duplicate.id AS old_id
FROM pack original JOIN pack duplicate
  ON duplicate.game_code=original.game_code AND duplicate.code=original.code
 AND duplicate.legacy_key=onepiece_numbered_pack_key(original.code)
CROSS JOIN LATERAL (
    SELECT bool_or(v.verified_don) AS has_don,
           bool_and(v.key_matches AND (v.collector_matches OR v.verified_don)) AS all_verified
    FROM (
        SELECT c.legacy_key IS NOT DISTINCT FROM 'catalog:ONEPIECE:'||original.code||':'||c.number
                 AND (NOT (c.specs ? 'productCode') OR c.specs->>'productCode' IS NOT DISTINCT FROM original.code) AS key_matches,
               coalesce(c.number ~ '^((OP|ST|EB|PRB)[0-9]{2}-[0-9]{3}|P-[0-9]{3})(_[a-zA-Z0-9]+)?$',false) AS collector_matches,
               coalesce(c.number ~ '^DON:don_[0-9]+$',false) AND c.specs @> '{"type":"don"}'
                 AND c.specs->>'productCode' IS NOT DISTINCT FROM original.code
                 AND c.source_url IS NOT DISTINCT FROM 'https://optcgapi.com/api/allDonCards/' AS verified_don
        FROM card c WHERE c.pack_id IN (original.id,duplicate.id) AND starts_with(c.legacy_key,'catalog:ONEPIECE:')
    ) v
) evidence
WHERE original.game_code='ONEPIECE' AND original.legacy_key='catalog:ONEPIECE:'||original.code
  AND original.superseded_by IS NULL AND duplicate.superseded_by IS NULL
  AND evidence.has_don AND evidence.all_verified
  AND (original.release_date IS NULL OR duplicate.release_date IS NULL OR original.release_date=duplicate.release_date)
  AND (original.release_label IS NULL OR duplicate.release_label IS NULL OR original.release_label=duplicate.release_label)
  AND (original.banner_key IS NULL OR duplicate.banner_key IS NULL OR original.banner_key=duplicate.banner_key)
  AND (original.metadata || duplicate.metadata) = (duplicate.metadata || original.metadata);

INSERT INTO onepiece_pack_label(pack_id,name)
SELECT m.keep_id,l.name FROM op57_merge m JOIN onepiece_pack_label l ON l.pack_id=m.old_id
UNION
SELECT m.keep_id,p.name FROM op57_merge m JOIN pack p ON p.id IN (m.keep_id,m.old_id)
ON CONFLICT DO NOTHING;
UPDATE pack p SET release_date=coalesce(p.release_date,d.release_date),
    release_label=coalesce(p.release_label,d.release_label),banner_key=coalesce(p.banner_key,d.banner_key),
    metadata=p.metadata||d.metadata,edit_version=p.edit_version+1
FROM op57_merge m JOIN pack d ON d.id=m.old_id
WHERE p.id=m.keep_id AND (p.release_date,p.release_label,p.banner_key,p.metadata) IS DISTINCT FROM
    (coalesce(p.release_date,d.release_date),coalesce(p.release_label,d.release_label),coalesce(p.banner_key,d.banner_key),p.metadata||d.metadata);
UPDATE card c SET pack_id=m.keep_id,edit_version=c.edit_version+1 FROM op57_merge m WHERE c.pack_id=m.old_id;
UPDATE pack p SET superseded_by=m.keep_id,edit_version=p.edit_version+1 FROM op57_merge m WHERE p.id=m.old_id;
