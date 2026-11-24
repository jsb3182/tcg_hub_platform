CREATE TABLE feed_provider_cooldown (
    provider text PRIMARY KEY,
    retry_after_at timestamptz NOT NULL
);

-- Older collectors saved X's shared bearer-token limit on the individual source.
INSERT INTO feed_provider_cooldown(provider, retry_after_at)
SELECT provider, max(retry_after_at)
FROM feed_source
WHERE provider = 'X' AND retry_after_at > now()
GROUP BY provider;
