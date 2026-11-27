LOCK TABLE card IN SHARE ROW EXCLUSIVE MODE;
CREATE TABLE catalog_search_cache (
    card_id bigint PRIMARY KEY,
    game_code text NOT NULL,
    facets jsonb NOT NULL
);

CREATE FUNCTION catalog_facet_keys(game text) RETURNS text[]
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    SELECT CASE game WHEN 'YUGIOH' THEN ARRAY['attribute','race','level','rank','link','atk','def']
        WHEN 'POKEMON' THEN ARRAY['type','stage','energyType','hp','regulation']
        WHEN 'WEISS' THEN ARRAY['type','color','level','cost','power','soul']
        WHEN 'ONEPIECE' THEN ARRAY['type','color','attribute','traits','cost','power','life']
        WHEN 'NIVEL' THEN ARRAY['type','attribute','cost','power','hit']
        WHEN 'RIFTBOUND' THEN ARRAY['type','domain','energy','might','power']
        ELSE ARRAY[]::text[] END
$$;

-- Isolate fields actually read by catalog_print_traits; a rules translation or image
-- refresh should not rewrite search indexes. Both legacy and normalized keys are kept.
CREATE FUNCTION catalog_facet_input(game text,s jsonb) RETURNS jsonb
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    SELECT coalesce(jsonb_object_agg(k,CASE WHEN k='regionalFacts'
        AND jsonb_typeof(s#>'{regionalFacts,ko}')='object'
        THEN jsonb_build_object('ko',(s#>'{regionalFacts,ko}')-'sourceUrl'-'productCode'-'counter')
        ELSE s->k END),'{}')
    FROM unnest(CASE game
        WHEN 'YUGIOH' THEN ARRAY['type','sub','attribute','at','race','rc','level','lv','rank','link','linkval','atk','def']
        WHEN 'POKEMON' THEN ARRAY['card_type','stage','types','hp','regulation']
        WHEN 'WEISS' THEN ARRAY['type','color','level','cost','power','soul']
        WHEN 'NIVEL' THEN ARRAY['type','attribute','cost','코스트','power','파워','hit','히트']
        WHEN 'RIFTBOUND' THEN ARRAY['type','domains','energy','might','power']
        WHEN 'ONEPIECE' THEN ARRAY['type','colors','attribute','traits','cost','power','life','regionalFacts']
        ELSE ARRAY[]::text[] END) k WHERE s ? k
$$;

CREATE FUNCTION catalog_indexed_facets(game text,s jsonb) RETURNS jsonb
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    WITH fields AS MATERIALIZED (
        SELECT key,catalog_print_traits(game,s,key) AS vals FROM unnest(catalog_facet_keys(game)) key
    )
    SELECT coalesce(jsonb_object_agg(key,vals) FILTER (WHERE cardinality(vals)>0),'{}') FROM fields
$$;

-- Rarities, alternate art and reprints share many identical rules. Calculate a
-- canonical facet object once per distinct rules combination during the first install.
WITH forms AS MATERIALIZED (
    SELECT game_code,catalog_facet_input(game_code,specs) AS rules,array_agg(id) AS ids
        FROM card WHERE status='PUBLISHED' GROUP BY game_code,catalog_facet_input(game_code,specs)
), calculated AS MATERIALIZED (
    SELECT game_code,ids,catalog_indexed_facets(game_code,rules) AS facets FROM forms
)
INSERT INTO catalog_search_cache(card_id,game_code,facets)
    SELECT unnest(ids),game_code,facets FROM calculated;

-- Validate the two foreign keys as sets, avoiding a row lock on every existing printing.
ALTER TABLE catalog_search_cache
    ADD FOREIGN KEY(card_id) REFERENCES card(id) ON DELETE CASCADE,
    ADD FOREIGN KEY(game_code) REFERENCES game(code);
CREATE INDEX catalog_search_values ON catalog_search_cache USING gin(facets jsonb_path_ops);
CREATE INDEX catalog_search_game ON catalog_search_cache(game_code,card_id);
ANALYZE catalog_search_cache;

CREATE FUNCTION update_catalog_search_cache() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE rules jsonb;
BEGIN
    IF NEW.status<>'PUBLISHED' THEN
        IF TG_OP='UPDATE' AND OLD.status='PUBLISHED' THEN
            DELETE FROM catalog_search_cache WHERE card_id=NEW.id;
        END IF;
        RETURN NEW;
    END IF;
    rules := catalog_facet_input(NEW.game_code,NEW.specs);
    IF TG_OP='UPDATE' AND OLD.status=NEW.status AND OLD.game_code=NEW.game_code
       AND catalog_facet_input(OLD.game_code,OLD.specs)=rules THEN
        RETURN NEW;
    END IF;
    INSERT INTO catalog_search_cache AS c VALUES (NEW.id,NEW.game_code,catalog_indexed_facets(NEW.game_code,rules))
        ON CONFLICT(card_id) DO UPDATE SET game_code=excluded.game_code,facets=excluded.facets
        WHERE (c.game_code,c.facets) IS DISTINCT FROM (excluded.game_code,excluded.facets);
    RETURN NEW;
END $$;
CREATE TRIGGER catalog_search_changed AFTER INSERT OR UPDATE OF game_code,specs,status ON card
FOR EACH ROW EXECUTE FUNCTION update_catalog_search_cache();
