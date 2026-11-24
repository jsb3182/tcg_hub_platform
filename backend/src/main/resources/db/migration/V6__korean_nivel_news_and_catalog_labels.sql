INSERT INTO feed_source(provider,source_key,label,game_code,auto_publish,interval_seconds,next_fetch_at)
VALUES ('OFFICIAL_NEWS','nivel-notice-kr','젬블로 니벨아레나 국내 공지','NIVEL',true,3600,now())
ON CONFLICT(provider,source_key) DO NOTHING;

UPDATE feed_source SET label='니벨아레나 일본 게임마켓 출전사 소식'
WHERE provider='OFFICIAL_NEWS' AND source_key='nivel-kr';

UPDATE feed_source AS s SET label=v.label FROM (VALUES
    ('YUGIOH','YGOPRODeck 유희왕 수록 목록'),
    ('WEISS','CCondeluci 바이스 슈발츠 영문 도감'),
    ('POKEMON','PTCG-database 포켓몬 한국어 도감'),
    ('NIVEL','젬블로 니벨아레나 공식 카드 목록'),
    ('RIFTBOUND','RiftHunt 리프트바운드 영문 도감')
) AS v(code,label)
WHERE s.provider='CATALOG' AND s.source_key=v.code;
