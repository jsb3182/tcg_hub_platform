ALTER TABLE feed_source
    ADD COLUMN policy_note text,
    ADD CONSTRAINT feed_source_policy_pause CHECK (policy_note IS NULL OR NOT enabled);

UPDATE feed_source
   SET enabled=false, state='BLOCKED', requested_at=NULL,
       policy_note='KONAMI 북미 이용 조건에 따라 자동 접근·번역·공개를 중지했습니다.'
 WHERE provider='OFFICIAL_NEWS' AND source_key='yugioh-en';

-- Keep the original moderation decision, posts, completed translations and last fetch for the audit trail.
UPDATE feed_item i SET translation_due_at=NULL
  FROM feed_source s WHERE i.source_id=s.id AND s.policy_note IS NOT NULL
   AND i.translation_due_at IS NOT NULL;
