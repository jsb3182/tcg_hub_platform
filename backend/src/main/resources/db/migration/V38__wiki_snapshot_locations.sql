ALTER TABLE wiki_card_document
    ADD COLUMN snapshot_row integer CHECK (snapshot_row>=0),
    ADD COLUMN article_sha256 text CHECK (article_sha256 ~ '^[0-9a-f]{64}$'),
    ADD CHECK ((snapshot_row IS NULL)=(article_sha256 IS NULL));
