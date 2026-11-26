-- Use the current printing on read, including cards imported before deck curves were added.
CREATE FUNCTION card_curve_value(game text, specs jsonb) RETURNS integer
LANGUAGE plpgsql IMMUTABLE PARALLEL SAFE STRICT AS $$
DECLARE
    printed text;
    cost jsonb;
    energy_count integer;
    minimum_cost integer;
    incomplete boolean := false;
BEGIN
    CASE game
        WHEN 'POKEMON' THEN
            IF jsonb_typeof(specs->'attacks') IS DISTINCT FROM 'array' THEN RETURN NULL; END IF;
            FOR cost IN SELECT attack->'cost' FROM jsonb_array_elements(specs->'attacks') attack LOOP
                IF jsonb_typeof(cost) IS DISTINCT FROM 'array' THEN
                    incomplete := true;
                ELSIF cost = '["No Energy Cost"]'::jsonb OR cost = '[]'::jsonb THEN
                    RETURN 0;
                ELSIF EXISTS (SELECT FROM jsonb_array_elements_text(cost) symbol
                    WHERE symbol IS NULL OR symbol NOT IN ('Grass','Fire','Water','Lightning','Psychic',
                        'Fighting','Dark','Darkness','Metal','Fairy','Dragon','Colorless','플러스')) THEN
                    incomplete := true;
                ELSE
                    -- The printed plus sign marks an optional extra effect, not a required energy.
                    SELECT count(*) INTO energy_count FROM jsonb_array_elements_text(cost) symbol WHERE symbol <> '플러스';
                    IF energy_count > 0 THEN minimum_cost := least(minimum_cost,energy_count);
                    ELSE incomplete := true; END IF;
                END IF;
            END LOOP;
            RETURN CASE WHEN NOT incomplete THEN minimum_cost END;
        WHEN 'YUGIOH' THEN
            IF coalesce(specs->>'type',specs->>'k','') !~* '(monster|몬스터)'
                OR concat_ws(' ',specs->>'type',specs->>'sub') ~* '(xyz|link|엑시즈|링크)' THEN RETURN NULL; END IF;
            printed := coalesce(specs->>'level',specs->>'lv');
        WHEN 'WEISS', 'ONEPIECE' THEN printed := specs->>'cost';
        WHEN 'NIVEL' THEN printed := coalesce(specs->>'코스트',specs->>'cost');
        WHEN 'RIFTBOUND' THEN printed := specs->>'energy';
        ELSE RETURN NULL;
    END CASE;
    RETURN CASE WHEN trim(printed) ~ '^[0-9]{1,3}$' THEN trim(printed)::integer END;
END $$;
