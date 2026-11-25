CREATE TABLE binder_card (
    owner_id bigint NOT NULL REFERENCES app_user ON DELETE CASCADE,
    card_id bigint NOT NULL REFERENCES card ON DELETE CASCADE,
    quantity integer NOT NULL CHECK (quantity BETWEEN 1 AND 9999),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(owner_id, card_id)
);
CREATE INDEX binder_updated ON binder_card(owner_id, updated_at DESC, card_id);

ALTER TABLE deck ADD COLUMN revision integer NOT NULL DEFAULT 1 CHECK (revision > 0);
ALTER TABLE deck ADD COLUMN state text NOT NULL DEFAULT 'DRAFT' CHECK (state IN ('DRAFT','COMPLETE'));
CREATE INDEX deck_owner_updated ON deck(owner_id, updated_at DESC, id);
CREATE TABLE deck_revision (
    deck_id bigint NOT NULL REFERENCES deck ON DELETE CASCADE,
    revision integer NOT NULL CHECK (revision > 0),
    saved_at timestamptz NOT NULL DEFAULT now(),
    snapshot jsonb NOT NULL CHECK (jsonb_typeof(snapshot)='object'),
    PRIMARY KEY(deck_id, revision)
);

-- Version 1 belongs to formats already present when V2 ran. Existing decks remain pinned.
INSERT INTO deck_rule(game_code,format,version,max_copies_per_card,details) VALUES
 ('YUGIOH','CONSTRUCTED',2,3,'{"source":"https://www.yugioh-card.com/en/rulebook/"}'),
 ('POKEMON','CONSTRUCTED',2,4,'{"source":"https://assets.pokemon.com/assets/cms2-sv-se/pdf/trading-card-game/rulebook/par_rulebook_en.pdf"}'),
 ('WEISS','CONSTRUCTED',2,4,'{"source":"https://en.ws-tcg.com/deck-construction-tips/"}'),
 ('NIVEL','CONSTRUCTED',2,3,'{"source":"https://nivelarena.jp/dlc/NivelArena_Tournament_Rules%28JP%29_Ver.1.02.pdf"}'),
 ('RIFTBOUND','CONSTRUCTED',2,3,'{"source":"https://cmsassets.rgpub.io/sanity/files/dsfx7636/news_live/e70866614d68a00a1cbd12c7de08124e0ea5e755.pdf"}');
INSERT INTO deck_section_rule(game_code,format,rule_version,section,min_cards,max_cards)
SELECT game,'CONSTRUCTED',2,section,minimum,maximum FROM (VALUES
 ('YUGIOH','MAIN',40,60),('YUGIOH','EXTRA',0,15),('YUGIOH','SIDE',0,15),
 ('POKEMON','MAIN',60,60),('WEISS','MAIN',50,50),
 ('NIVEL','MAIN',40,40),('NIVEL','LEADER',1,1),
 ('RIFTBOUND','MAIN',40,40),('RIFTBOUND','RUNE',12,12),('RIFTBOUND','LEGEND',1,1),
 ('RIFTBOUND','BATTLEFIELD',3,3),('RIFTBOUND','SIDE',0,8)
) AS limits(game,section,minimum,maximum);
