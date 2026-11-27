ALTER TABLE card_korean_reading ADD COLUMN basis text NOT NULL DEFAULT 'MACHINE_TRANSLATION'
    CHECK (basis IN ('MACHINE_TRANSLATION','CURATED_TRANSLATION'));

CREATE FUNCTION catalog_print_traits(game text,s jsonb,facet text) RETURNS text[]
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    SELECT CASE WHEN game='ONEPIECE' AND facet='attribute' AND nullif(s#>>'{regionalFacts,ko,attribute}','') IS NOT NULL
        THEN regexp_split_to_array(s#>>'{regionalFacts,ko,attribute}','\s*/\s*')
        ELSE catalog_trait_values(game,
            CASE WHEN game='ONEPIECE' AND jsonb_typeof(s#>'{regionalFacts,ko}')='object'
                 THEN s||jsonb_strip_nulls(s#>'{regionalFacts,ko}') ELSE s END,facet) END
$$;
