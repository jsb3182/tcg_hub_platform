-- A dated announcement belongs to a printing's product only when its catalog identity is unique.
CREATE VIEW catalog_pack_date AS
WITH matches AS (
    SELECT e.id, min(p.id) AS pack_id, min(e.release_date) AS release_date
    FROM product_release e JOIN pack p ON p.game_code=e.game_code
      AND (e.catalog_code IS NOT NULL OR e.catalog_name IS NOT NULL)
      AND (e.catalog_code IS NULL OR upper(p.code)=upper(e.catalog_code))
      AND (e.catalog_name IS NULL OR lower(p.name)=lower(e.catalog_name))
      AND CASE WHEN e.game_code='YUGIOH' AND starts_with(e.product_key,'na-premiere:')
               THEN p.metadata @> '{"wp":true,"sec":true}' ELSE starts_with(p.legacy_key,'catalog:') END
    GROUP BY e.id HAVING count(*)=1
), announced AS (
    SELECT pack_id,min(release_date) AS release_date FROM matches GROUP BY pack_id
)
SELECT p.id AS pack_id,p.game_code,coalesce(p.release_date,a.release_date) AS release_date
FROM pack p LEFT JOIN announced a ON a.pack_id=p.id
WHERE coalesce(p.release_date,a.release_date) IS NOT NULL;

CREATE INDEX card_catalog_release ON card(game_code,release_date) WHERE status='PUBLISHED';

CREATE FUNCTION catalog_trait_label(game text,facet text,v text) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    SELECT CASE
    WHEN game='YUGIOH' AND facet='attribute' THEN coalesce(
        '{"빛":"LIGHT","光":"LIGHT","어둠":"DARK","闇":"DARK","땅":"EARTH","地":"EARTH","물":"WATER","水":"WATER",
          "바람":"WIND","風":"WIND","화염":"FIRE","炎":"FIRE","신":"DIVINE","神":"DIVINE"}'::jsonb->>v,upper(v))
    WHEN game='YUGIOH' AND facet='race' THEN coalesce(
        '{"마법사족":"Spellcaster","魔法使い族":"Spellcaster","악마족":"Fiend","悪魔族":"Fiend","전사족":"Warrior","戦士族":"Warrior",
          "드래곤족":"Dragon","ドラゴン族":"Dragon","기계족":"Machine","機械族":"Machine","물족":"Aqua","水族":"Aqua",
          "언데드족":"Zombie","アンデット族":"Zombie","천사족":"Fairy","天使族":"Fairy","야수족":"Beast","獣族":"Beast",
          "곤충족":"Insect","昆虫族":"Insect","식물족":"Plant","植物族":"Plant","사이버스족":"Cyberse","サイバース族":"Cyberse",
          "비행야수족":"Winged Beast","鳥獣族":"Winged Beast","암석족":"Rock","岩石族":"Rock","야수전사족":"Beast-Warrior","獣戦士族":"Beast-Warrior",
          "공룡족":"Dinosaur","恐竜族":"Dinosaur","사이킥족":"Psychic","サイキック族":"Psychic","환상마족":"Illusion","幻想魔族":"Illusion",
          "파충류족":"Reptile","爬虫類族":"Reptile","어류족":"Fish","魚族":"Fish","번개족":"Thunder","雷族":"Thunder",
          "화염족":"Pyro","炎族":"Pyro","해룡족":"Sea Serpent","海竜族":"Sea Serpent","환신야수족":"Divine-Beast","幻神獣族":"Divine-Beast",
          "창조신족":"Creator God","創造神族":"Creator God","환룡족":"Wyrm","幻竜族":"Wyrm"}'::jsonb->>v,v)
    ELSE v END
$$;

-- Return one value for each color/type/domain so multicolor cards match each of their colors.
CREATE FUNCTION catalog_trait_values(game text,s jsonb,facet text) RETURNS text[]
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    WITH value AS (
        SELECT CASE
            WHEN game='YUGIOH' AND facet='level' AND concat_ws(' ',s->>'type',s->>'sub') ~* 'xyz|link|엑시즈|링크' THEN NULL
            WHEN game='YUGIOH' AND facet='rank' AND concat_ws(' ',s->>'type',s->>'sub') ~* 'xyz|엑시즈' THEN coalesce(s->'level',s->'lv')
            WHEN game='YUGIOH' AND facet='link' AND concat_ws(' ',s->>'type',s->>'sub') ~* 'link|링크' THEN coalesce(s->'linkval',s->'lv')
            WHEN game='YUGIOH' AND facet='level' THEN coalesce(s->'level',s->'lv')
            WHEN game='YUGIOH' AND facet='attribute' THEN coalesce(s->'attribute',s->'at')
            WHEN game='YUGIOH' AND facet='race' THEN coalesce(s->'rc',CASE WHEN s->>'type' ILIKE '%Monster' OR s->>'type'='Token' THEN s->'race' END)
            WHEN game='NIVEL' AND facet='cost' THEN coalesce(s->'코스트',s->'cost')
            WHEN game='NIVEL' AND facet='hit' THEN coalesce(s->'히트',s->'hit')
            WHEN game='NIVEL' AND facet='power' THEN coalesce(s->'파워',s->'power')
            WHEN game='POKEMON' AND facet='type' THEN s->'card_type'
            WHEN game='POKEMON' AND facet='energyType' THEN s->'types'
            WHEN game='ONEPIECE' AND facet='color' THEN s->'colors'
            WHEN game='RIFTBOUND' AND facet='domain' THEN s->'domains'
            ELSE s->facet END AS raw
    )
    SELECT ARRAY(
        SELECT DISTINCT catalog_trait_label(game,facet,trim(item #>> '{}')) FROM value
        CROSS JOIN LATERAL jsonb_array_elements(CASE WHEN jsonb_typeof(raw)='array' THEN raw ELSE jsonb_build_array(raw) END) item
        WHERE jsonb_typeof(item) IN ('number','string') AND length(trim(item #>> '{}')) BETWEEN 1 AND 80
          AND (facet NOT IN ('atk','def','rank','level','link','hp','life','power','soul','cost','energy','might','hit')
               OR trim(item #>> '{}') ~ '^[0-9]{1,8}$')
    )
$$;
