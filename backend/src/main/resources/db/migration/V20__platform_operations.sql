CREATE TABLE collection_control (
    singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
    crawler_enabled boolean NOT NULL DEFAULT true,
    scheduler_enabled boolean NOT NULL DEFAULT true,
    spring_managed boolean NOT NULL DEFAULT false
);
INSERT INTO collection_control DEFAULT VALUES;
ALTER TABLE feed_source ADD COLUMN schedule_ready boolean NOT NULL DEFAULT false;
ALTER TABLE feed_item ADD COLUMN hidden boolean NOT NULL DEFAULT false,
                      ADD COLUMN pinned boolean NOT NULL DEFAULT false;
ALTER TABLE store ADD COLUMN official boolean,
                  ADD COLUMN edit_version integer NOT NULL DEFAULT 1;

-- Official status is known for the publisher's authorized-store listing. Other shops stay unclassified.
CREATE FUNCTION public_store_official(shop_id bigint, override_value boolean) RETURNS boolean
LANGUAGE sql STABLE AS $$
    SELECT coalesce(override_value, CASE WHEN EXISTS (SELECT FROM store_game
        WHERE store_id=shop_id AND game_code='YUGIOH' AND evidence_url='https://www.yugioh.co.kr/site/event_store.php?code=store')
        THEN true END);
$$;

-- Keep operator-approved addresses, visibility and games when the quarterly directory is refreshed.
CREATE OR REPLACE FUNCTION apply_semas_directory(edition date, rows jsonb) RETURNS void LANGUAGE plpgsql AS $$
BEGIN
    IF edition IS NULL OR jsonb_typeof(rows) IS DISTINCT FROM 'array' OR jsonb_array_length(rows)=0 THEN
        RAISE EXCEPTION 'Expected a complete nonempty directory';
    END IF;
    INSERT INTO store_directory_edition VALUES ('SEMAS',edition)
    ON CONFLICT(provider) DO UPDATE SET as_of=EXCLUDED.as_of WHERE store_directory_edition.as_of<=EXCLUDED.as_of;
    IF NOT FOUND THEN RAISE EXCEPTION 'Cannot replace the directory with an older edition'; END IF;

    INSERT INTO store AS s(semas_id,name,address,region,source_date,location,hours)
        SELECT key,name,address,region,edition,ST_SetSRID(ST_MakePoint(lon,lat),4326)::geography,hours
          FROM jsonb_to_recordset(rows) AS r(key text,name text,address text,region text,lon float8,lat float8,hours jsonb)
    ON CONFLICT(semas_id) DO UPDATE SET name=EXCLUDED.name,address=EXCLUDED.address,region=EXCLUDED.region,
        source_date=edition,location=EXCLUDED.location,hours=EXCLUDED.hours,listed=true WHERE s.edit_version=1;
    UPDATE store s SET listed=false WHERE s.semas_id IS NOT NULL AND s.listed AND s.edit_version=1 AND NOT EXISTS
        (SELECT FROM jsonb_array_elements(rows) AS r WHERE r->>'key'=s.semas_id);

    DELETE FROM store_game g USING store s WHERE g.store_id=s.id AND g.directory_managed AND s.semas_id IS NOT NULL AND s.edit_version=1;
    INSERT INTO store_game(store_id,game_code,evidence_url,checked_on,directory_managed)
        SELECT s.id,e.key,e.value,coalesce(r.checked,edition),true FROM jsonb_to_recordset(rows) AS r(key text,games jsonb,checked date)
        JOIN store s ON s.semas_id=r.key AND s.edit_version=1 CROSS JOIN LATERAL jsonb_each_text(r.games) AS e
    ON CONFLICT(store_id,game_code) DO NOTHING;
END $$;
