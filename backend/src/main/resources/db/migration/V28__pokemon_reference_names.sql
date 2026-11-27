-- Existing installations already have matched regional printings. Reuse only their names.
WITH printed AS MATERIALIZED (
    SELECT c.id,c.name,c.specs->>'pokedex_number' AS species,lang,
           nullif(c.specs->'names'->>lang,'') AS printed_name,c.specs->'sources'->>lang AS source_url
    FROM card c
    JOIN feed_source f ON f.id=c.source_id AND f.provider='CATALOG' AND f.game_code='POKEMON'
    CROSS JOIN (VALUES ('en'),('ja')) AS target(lang)
    WHERE c.game_code='POKEMON' AND starts_with(c.legacy_key,'catalog:POKEMON:ko:')
      AND c.specs->>'card_type'='Pokémon' AND c.specs->>'language'='ko'
      AND jsonb_typeof(c.specs->'pokedex_number')='number' AND c.specs->>'pokedex_number' ~ '^[1-9][0-9]*$'
), agreed AS (
    SELECT species,name,lang,min(printed_name COLLATE "C") AS printed_name,
           min(source_url COLLATE "C") FILTER (WHERE
               (lang='en' AND (starts_with(source_url,'https://pkmncards.com/card/')
                              OR starts_with(source_url,'https://www.pokemon.com/us/pokemon-tcg/pokemon-cards/')))
               OR (lang='ja' AND starts_with(source_url,'https://www.pokemon-card.com/card-search/details.php/card/'))
           ) AS source_url
    FROM printed WHERE printed_name IS NOT NULL
    GROUP BY species,name,lang HAVING count(DISTINCT printed_name COLLATE "C")=1
), additions AS (
    SELECT p.id,jsonb_object_agg(p.lang,a.printed_name) AS names,
           jsonb_object_agg(p.lang,a.source_url) FILTER (WHERE a.source_url IS NOT NULL) AS urls
    FROM printed p JOIN agreed a USING(species,name,lang)
    WHERE p.printed_name IS NULL
    GROUP BY p.id
)
UPDATE card c SET specs=c.specs || jsonb_strip_nulls(jsonb_build_object('referenceNames',a.names,'referenceNameUrls',a.urls))
FROM additions a WHERE c.id=a.id;
