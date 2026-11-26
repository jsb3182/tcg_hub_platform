-- Textual evidence for a specific imported printing. Card and variant data retain their own ownership.
CREATE TABLE legacy_card_edition (
    card_id bigint PRIMARY KEY REFERENCES card(id) ON DELETE CASCADE,
    matched_number text NOT NULL,
    matched_name text NOT NULL,
    names jsonb NOT NULL CHECK (jsonb_typeof(names) = 'object'),
    texts jsonb NOT NULL CHECK (jsonb_typeof(texts) = 'object'),
    source_url text NOT NULL,
    konami_id bigint
);
