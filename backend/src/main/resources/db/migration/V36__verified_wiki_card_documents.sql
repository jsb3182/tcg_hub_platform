CREATE TABLE wiki_card_document (
    game_code text NOT NULL REFERENCES game(code),
    lookup_key text NOT NULL,
    passcode text,
    printing_number text,
    title text NOT NULL CHECK (length(title) BETWEEN 1 AND 255),
    document_url text NOT NULL CHECK (document_url LIKE 'https://namu.wiki/w/%'),
    revision text,
    snapshot_date date NOT NULL,
    snapshot_url text NOT NULL,
    verification_url text NOT NULL,
    names jsonb NOT NULL CHECK (jsonb_typeof(names)='object' AND names ? 'ko'),
    facts jsonb NOT NULL CHECK (jsonb_typeof(facts)='object'),
    PRIMARY KEY (game_code,lookup_key),
    CHECK ((game_code='YUGIOH' AND lookup_key ~ '^cid:[1-9][0-9]{0,9}$')
        OR (starts_with(lookup_key,'catalog:'||game_code||':') AND printing_number IS NOT NULL)),
    CHECK (passcode IS NULL OR passcode ~ '^[1-9][0-9]{0,7}$')
);
