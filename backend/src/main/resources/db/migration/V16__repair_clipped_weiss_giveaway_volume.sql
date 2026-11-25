-- Older M2M100 output can be a copy of the English headline with only the
-- volume digits missing. Repair that fingerprint without replacing edited translations.
WITH giveaways AS (
    SELECT i.id, i.payload->>'title' AS original,
           regexp_match(i.payload->>'title',
               '^(?:【Giveaway】|\[Giveaway\])[[:blank:]]*(Booster Pack|Extra Booster|Premium Booster)[[:blank:]]+(.+[[:blank:]]+Vol\.[[:blank:]]*[0-9]+)([[:blank:]]+Winners)?$') AS parts
      FROM feed_item i JOIN feed_source s ON s.id=i.source_id
     WHERE s.provider='OFFICIAL_NEWS' AND s.source_key='weiss-en' AND s.policy_note IS NULL
       AND i.status IN ('PENDING','PUBLISHED') AND i.payload->>'kind'='NEWS' AND i.original_language='en'
)
UPDATE feed_item_translation t
   SET title=g.parts[2] || ' ' || CASE g.parts[1]
           WHEN 'Booster Pack' THEN '부스터 팩'
           WHEN 'Extra Booster' THEN '엑스트라 부스터'
           WHEN 'Premium Booster' THEN '프리미엄 부스터' END ||
       CASE WHEN g.parts[3] IS NULL THEN ' 증정 이벤트' ELSE ' 증정 이벤트 당첨자 발표' END
  FROM giveaways g
 WHERE t.item_id=g.id AND t.lang='ko' AND g.parts IS NOT NULL
   AND t.title=regexp_replace(g.original,'(Vol\.)[[:blank:]]*[0-9]+([[:blank:]]+Winners)?$','\1\2');
