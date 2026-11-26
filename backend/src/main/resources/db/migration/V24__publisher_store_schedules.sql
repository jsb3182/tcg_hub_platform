ALTER TABLE store_game ADD COLUMN publisher_source_id bigint REFERENCES feed_source;
ALTER TABLE calendar_event
    ADD COLUMN schedule_source_id bigint REFERENCES feed_source,
    ADD COLUMN schedule_notice text,
    ADD COLUMN schedule_slot text,
    ADD COLUMN schedule_url text,
    ADD COLUMN schedule_expected jsonb,
    ADD CONSTRAINT calendar_publisher_fields CHECK (
        num_nonnulls(schedule_source_id,schedule_notice,schedule_slot,schedule_url,schedule_expected) IN (0,5)),
    ADD CONSTRAINT calendar_publisher_slot UNIQUE(schedule_source_id,schedule_notice,store_id,schedule_slot);

INSERT INTO feed_source(provider,source_key,label,game_code,auto_publish,interval_seconds,next_fetch_at) VALUES
 ('STORE_SCHEDULE','onepiece-kr-official-shops','반다이남코코리아 원피스 공인 점포','ONEPIECE',true,604800,now()),
 ('STORE_SCHEDULE','onepiece-kr-events','반다이남코코리아 원피스 점포별 대회 일정','ONEPIECE',true,86400,now());

CREATE OR REPLACE FUNCTION public_store_official(shop_id bigint, override_value boolean) RETURNS boolean
LANGUAGE sql STABLE AS $$
 SELECT coalesce(override_value,CASE WHEN EXISTS (
     SELECT FROM store_game WHERE store_id=shop_id AND
       ((game_code='YUGIOH' AND evidence_url='https://www.yugioh.co.kr/site/event_store.php?code=store')
         OR (game_code='ONEPIECE' AND evidence_url='https://onepiece-cardgame.kr/officialshoplist.do')))
     THEN true END);
$$;
