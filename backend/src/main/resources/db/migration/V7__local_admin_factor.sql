CREATE TABLE local_admin_factor (
    user_id bigint PRIMARY KEY REFERENCES app_user(id) ON DELETE CASCADE,
    secret_base32 text NOT NULL CHECK (secret_base32 ~ '^[A-Z2-7]{32}$'),
    last_step bigint CHECK (last_step >= 0)
);

CREATE TABLE local_admin_session (
    token_hash text PRIMARY KEY CHECK (token_hash ~ '^[0-9a-f]{64}$'),
    user_id bigint NOT NULL REFERENCES local_admin_factor(user_id) ON DELETE CASCADE,
    expires_at timestamptz NOT NULL
);
CREATE INDEX local_admin_session_user ON local_admin_session(user_id);
CREATE INDEX local_admin_session_expiry ON local_admin_session(expires_at);
