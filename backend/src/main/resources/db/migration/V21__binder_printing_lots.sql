-- Existing copies have no recorded physical edition or condition.
ALTER TABLE binder_card ADD COLUMN edition text NOT NULL DEFAULT 'und' CHECK (edition IN ('und','ko','en','ja')),
    ADD COLUMN condition text NOT NULL DEFAULT 'UNSPECIFIED' CHECK (condition IN ('UNSPECIFIED','NM','LP','MP','HP','DMG')),
    ADD COLUMN tradable boolean NOT NULL DEFAULT false;
ALTER TABLE binder_card DROP CONSTRAINT binder_card_pkey,
    ADD PRIMARY KEY(owner_id,card_id,edition,condition,tradable);
