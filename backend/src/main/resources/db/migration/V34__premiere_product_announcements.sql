-- The North American publisher describes the entire product. The World Premiere
-- gallery counts only the printings catalogued in that section of the hub.
CREATE TABLE yugioh_na_product (
    code text PRIMARY KEY,
    english_name text NOT NULL,
    launch_date date NOT NULL,
    ots_date date NOT NULL CHECK (ots_date <= launch_date),
    set_size integer NOT NULL CHECK (set_size > 0),
    source_url text NOT NULL UNIQUE CHECK (source_url LIKE 'https://www.yugioh-card.com/en/products/%')
);

INSERT INTO yugioh_na_product VALUES
    ('CORI','Chaos Origins','2026-07-03','2026-07-01',100,'https://www.yugioh-card.com/en/products/cori/'),
    ('LAVD','Legendary ARC-V Decks','2026-08-07','2026-08-05',168,'https://www.yugioh-card.com/en/products/lavd/'),
    ('BETB','Beyond the Brave','2026-10-09','2026-10-07',100,'https://www.yugioh-card.com/en/products/betb/'),
    ('IMPH','Immortal Phoenix','2027-01-29','2027-01-27',100,'https://www.yugioh-card.com/en/products/imph/'),
    ('MZMC','Maze of Machines','2027-03-19','2027-03-17',153,'https://www.yugioh-card.com/en/products/mzmc/');

-- Keep existing shared pack URLs. A fresh install can show the announcements
-- before loading any cards. The legacy importer adopts these rows by code.
INSERT INTO pack(game_code,name,code,release_date,metadata,legacy_key)
SELECT 'YUGIOH',titles.ko,n.code,n.launch_date,
       jsonb_build_object('sec',true,'wp',true),'publisher:na-tcg:premiere:' || n.code
FROM yugioh_na_product n
JOIN (VALUES ('CORI','카오스 오리진스'), ('LAVD','레전더리 아크파이브 덱'),
             ('BETB','비욘드 더 브레이브'), ('IMPH','임모털 피닉스'),
             ('MZMC','메이즈 오브 머신즈')) titles(code,ko) USING (code)
WHERE NOT EXISTS (SELECT 1 FROM pack p WHERE p.game_code='YUGIOH' AND p.code=n.code
                    AND p.metadata @> '{"sec":true,"wp":true}');
