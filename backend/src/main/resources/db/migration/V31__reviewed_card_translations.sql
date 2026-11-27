CREATE TABLE card_translation (
    card_id bigint NOT NULL REFERENCES card(id) ON DELETE CASCADE,
    lang varchar(2) NOT NULL CHECK (lang IN ('ko','en','ja')),
    name varchar(320),
    effect text CHECK (length(effect) <= 8000),
    source_url varchar(2048),
    basis text CHECK (basis IN ('PRINTED_NAME','TRANSLATED_NAME')),
    version bigint NOT NULL CHECK (version > 0),
    PRIMARY KEY (card_id,lang),
    CHECK ((name IS NULL AND effect IS NULL AND source_url IS NULL AND basis IS NULL)
        OR ((name IS NOT NULL OR effect IS NOT NULL) AND source_url IS NOT NULL AND basis IS NOT NULL))
);
