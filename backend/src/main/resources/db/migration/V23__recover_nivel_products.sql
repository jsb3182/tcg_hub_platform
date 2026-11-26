-- Previous imports folded the product label into a JSON key after the effect heading.
-- Only repair publisher-owned rows for which the original detail contains one product.
CREATE TEMP TABLE nivel_product_repair ON COMMIT DROP AS
SELECT c.id AS card_id, p.id AS old_pack, p.code, field.key, trim(field.value) AS product
FROM card c JOIN pack p ON p.id=c.pack_id
JOIN feed_source s ON s.id=c.source_id AND s.provider='CATALOG' AND s.source_key='NIVEL'
CROSS JOIN LATERAL (
    SELECT key,value,count(*) OVER () AS matches FROM jsonb_each_text(c.specs)
    WHERE starts_with(key,E'효과\n') AND right(key,length(E'\n제품명'))=E'\n제품명' AND trim(value)<>''
) field
WHERE c.game_code='NIVEL' AND p.game_code='NIVEL' AND p.name=p.code AND p.edit_version=1
  AND starts_with(p.legacy_key,'catalog:NIVEL:') AND field.matches=1;

-- Keep the old numeric pack ID for its largest product, even when several products used one code.
WITH ranked AS (
    SELECT old_pack, product, row_number() OVER (PARTITION BY old_pack ORDER BY count(*) DESC,product COLLATE "C") AS ordinal
    FROM nivel_product_repair GROUP BY old_pack, product
)
UPDATE pack p SET name=r.product,edit_version=edit_version+1 FROM ranked r
WHERE p.id=r.old_pack AND r.ordinal=1 AND NOT EXISTS (
    SELECT FROM pack named WHERE named.game_code='NIVEL' AND named.code=p.code AND named.name=r.product
);

INSERT INTO pack(game_code,code,name,legacy_key)
SELECT DISTINCT 'NIVEL',r.code,r.product,'catalog:NIVEL:edition:'||
       encode(sha256(convert_to(jsonb_build_array(r.code,r.product)::text,'UTF8')),'hex')
FROM nivel_product_repair r WHERE NOT EXISTS (
    SELECT FROM pack p WHERE p.game_code='NIVEL' AND p.code=r.code AND p.name=r.product
) ON CONFLICT(legacy_key) DO NOTHING;

UPDATE card c SET pack_id=p.id,specs=c.specs-r.key,edit_version=c.edit_version+1
FROM nivel_product_repair r JOIN LATERAL (
    SELECT id FROM pack WHERE game_code='NIVEL' AND code=r.code AND name=r.product
    ORDER BY (id=r.old_pack) DESC,id LIMIT 1
) p ON true WHERE c.id=r.card_id;
