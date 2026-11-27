CREATE TABLE supplemental_printing (
    provider text NOT NULL, game_code text NOT NULL REFERENCES game(code), external_id text NOT NULL,
    card_id bigint REFERENCES card(id) ON DELETE SET NULL, pack_code text, number text NOT NULL,
    name text NOT NULL, lang text NOT NULL CHECK(lang IN ('ko','ja','en','und')), effect text,
    facts jsonb NOT NULL DEFAULT '{}',source_url text NOT NULL, updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(provider,game_code,external_id)
);
CREATE INDEX supplemental_card_field ON supplemental_printing(card_id,lang) WHERE card_id IS NOT NULL;
CREATE INDEX card_public_number ON card(game_code,lower(number)) WHERE status='PUBLISHED';
CREATE TABLE provider_configuration(provider text PRIMARY KEY,requires_key boolean NOT NULL,configured boolean NOT NULL);
INSERT INTO feed_source(provider,source_key,game_code,label,auto_publish,interval_seconds,next_fetch_at)
SELECT provider,game,game,label,true,86400,now() FROM (VALUES
    ('APITCG','ONEPIECE','API TCG · 원피스 인쇄본·시세'),
    ('TCGSTUDIO','WEISS','Trading Card Studio · 바이스 슈발츠'),('TCGSTUDIO','NIVEL','Trading Card Studio · 니벨아레나'),
    ('RIFTCODEX','RIFTBOUND','Riftcodex · 인쇄본 식별자'),('RIOT','RIFTBOUND','Riot Games · 공식 카드 콘텐츠'),
    ('TCGDEX','POKEMON','TCGdex · 한국어 도감'),('WIKI_INDEX','YUGIOH','나무위키 · 검증한 카드 자료')
) providers(provider,game,label);
