-- A Korean printed card number identifies a printing of the same Konami card.
-- A product date is supplied only when its Korean contents independently match.
CREATE TABLE yugioh_korean_print (
    konami_id bigint PRIMARY KEY CHECK (konami_id > 0),
    number text NOT NULL CHECK (length(number) BETWEEN 1 AND 48),
    yaml_revision text NOT NULL CHECK (yaml_revision ~ '^[0-9a-f]{40}$'),
    yaml_file text NOT NULL CHECK (yaml_file ~ '^(kdb)?[0-9]+[.]json$'),
    product_released_on date,
    product_id uuid,
    CHECK ((product_released_on IS NULL) = (product_id IS NULL))
);
