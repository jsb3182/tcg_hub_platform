ALTER TABLE pack ADD COLUMN edit_version bigint NOT NULL DEFAULT 1 CHECK (edit_version > 0);
ALTER TABLE card ADD COLUMN edit_version bigint NOT NULL DEFAULT 1 CHECK (edit_version > 0);
