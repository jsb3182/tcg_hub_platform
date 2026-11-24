-- A saved deck pins the rule version used to validate its contents.
CREATE TABLE deck_rule (
    game_code text NOT NULL REFERENCES game,
    format text NOT NULL,
    version integer NOT NULL CHECK (version > 0),
    max_copies_per_card smallint CHECK (max_copies_per_card > 0),
    details jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(details)='object'),
    PRIMARY KEY(game_code,format,version)
);
CREATE TABLE deck_section_rule (
    game_code text NOT NULL,
    format text NOT NULL,
    rule_version integer NOT NULL,
    section text NOT NULL,
    min_cards smallint CHECK (min_cards >= 0),
    max_cards smallint CHECK (max_cards >= 0),
    CHECK (max_cards IS NULL OR min_cards IS NULL OR max_cards >= min_cards),
    PRIMARY KEY(game_code,format,rule_version,section),
    FOREIGN KEY(game_code,format,rule_version) REFERENCES deck_rule(game_code,format,version)
);

-- Existing formats and labels have no known size limits until verified by a game editor.
INSERT INTO deck_rule(game_code,format,version)
SELECT DISTINCT game_code,format,1 FROM deck;
INSERT INTO deck_section_rule(game_code,format,rule_version,section)
SELECT DISTINCT d.game_code,d.format,1,e.section FROM deck d JOIN deck_entry e ON d.id=e.deck_id;

ALTER TABLE deck ADD COLUMN rule_version integer NOT NULL DEFAULT 1;
ALTER TABLE deck ADD FOREIGN KEY(game_code,format,rule_version) REFERENCES deck_rule(game_code,format,version);
ALTER TABLE deck ADD UNIQUE(id,game_code,format,rule_version);

ALTER TABLE deck_entry ADD COLUMN format text;
ALTER TABLE deck_entry ADD COLUMN rule_version integer;
UPDATE deck_entry e SET format=d.format,rule_version=d.rule_version FROM deck d WHERE d.id=e.deck_id;
ALTER TABLE deck_entry ALTER COLUMN format SET NOT NULL;
ALTER TABLE deck_entry ALTER COLUMN rule_version SET NOT NULL;
ALTER TABLE deck_entry DROP CONSTRAINT deck_entry_game_code_deck_id_fkey;
ALTER TABLE deck_entry ADD FOREIGN KEY(deck_id,game_code,format,rule_version)
    REFERENCES deck(id,game_code,format,rule_version) ON DELETE CASCADE;
ALTER TABLE deck_entry ADD FOREIGN KEY(game_code,format,rule_version,section)
    REFERENCES deck_section_rule(game_code,format,rule_version,section);
