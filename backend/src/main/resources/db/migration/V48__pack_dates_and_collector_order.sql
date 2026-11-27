-- A manually chosen pack is an exact identity. Clearing it detaches that calendar entry.
CREATE OR REPLACE VIEW catalog_pack_date AS
WITH matches AS (
    SELECT e.selected_pack_id AS pack_id, e.release_date
    FROM product_release e WHERE e.selected_pack_id IS NOT NULL
    UNION ALL
    SELECT min(p.id), min(e.release_date)
    FROM product_release e JOIN pack p ON p.game_code=e.game_code
      AND (e.catalog_code IS NOT NULL OR e.catalog_name IS NOT NULL)
      AND (e.catalog_code IS NULL OR upper(p.code)=upper(e.catalog_code))
      AND (e.catalog_name IS NULL OR lower(p.name)=lower(e.catalog_name))
      AND CASE WHEN e.game_code='YUGIOH' AND starts_with(e.product_key,'na-premiere:')
               THEN p.metadata @> '{"wp":true,"sec":true}' ELSE starts_with(p.legacy_key,'catalog:') END
    WHERE NOT e.manual AND e.selected_pack_id IS NULL
    GROUP BY e.id HAVING count(*)=1
), announced AS (
    SELECT pack_id,min(release_date) AS release_date FROM matches GROUP BY pack_id
)
SELECT p.id AS pack_id,p.game_code,coalesce(p.release_date,a.release_date) AS release_date
FROM pack p LEFT JOIN announced a ON a.pack_id=p.id
WHERE coalesce(p.release_date,a.release_date) IS NOT NULL;

CREATE INDEX release_selected_pack ON product_release(selected_pack_id) WHERE selected_pack_id IS NOT NULL;

-- Compare every digit run by its decimal magnitude without casting or truncating long collector codes.
CREATE FUNCTION catalog_collector_order(number text) RETURNS text[]
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS $$
    SELECT array_agg(CASE WHEN token ~ '^[0-9]' THEN
            '0'||lpad(length(trim(leading '0' from token))::text,6,'0')||trim(leading '0' from token)
            ELSE '1'||lower(token COLLATE "C") END ORDER BY position)
    FROM (SELECT part[1] AS token,position FROM regexp_matches(number,'[0-9]+|[^0-9]+','g')
          WITH ORDINALITY AS parts(part,position)) tokens
$$;
