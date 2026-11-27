ALTER TABLE deck ADD COLUMN name_ja varchar(100) NOT NULL DEFAULT '',
                 ADD COLUMN name_en varchar(100) NOT NULL DEFAULT '';
ALTER TABLE card_variant ADD UNIQUE (card_id,id);
ALTER TABLE deck_entry ADD COLUMN variant_id bigint,
                       ADD COLUMN display_order integer NOT NULL DEFAULT 0;
ALTER TABLE deck_entry ADD FOREIGN KEY (card_id,variant_id) REFERENCES card_variant(card_id,id);
ALTER TABLE deck_entry DROP CONSTRAINT deck_entry_pkey;
CREATE UNIQUE INDEX deck_entry_default_print ON deck_entry(deck_id,section,card_id) WHERE variant_id IS NULL;
CREATE UNIQUE INDEX deck_entry_chosen_print ON deck_entry(deck_id,section,card_id,variant_id) WHERE variant_id IS NOT NULL;
CREATE TABLE deck_decoration (
    deck_id bigint NOT NULL REFERENCES deck ON DELETE CASCADE,
    slot text NOT NULL CHECK (slot IN ('cover','main','extra')),
    storage_key text NOT NULL,
    PRIMARY KEY (deck_id,slot)
);
