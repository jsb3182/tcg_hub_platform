INSERT INTO feed_source(provider,source_key,label,game_code,auto_publish,interval_seconds,next_fetch_at)
VALUES
 ('X','YuGiOh_TCG','Yu-Gi-Oh! TCG · X','YUGIOH',false,3600,now()),
 ('X','weissschwarz_en','Weiß Schwarz · X','WEISS',false,3600,now()),
 ('X','PokemonTCG','Pokémon TCG · X','POKEMON',false,3600,now()),
 ('X','NivelArena','니벨아레나 · X','NIVEL',false,3600,now()),
 ('X','PlayRiftbound','Riftbound · X','RIFTBOUND',false,3600,now()),
 ('OFFICIAL_NEWS','yugioh-en','KONAMI 유희왕 공지','YUGIOH',true,3600,now()),
 ('OFFICIAL_NEWS','weiss-en','부시로드 바이스 슈발츠 공지','WEISS',true,3600,now()),
 ('OFFICIAL_NEWS','pokemon-jp','포켓몬 카드 일본 공지','POKEMON',true,3600,now()),
 ('OFFICIAL_NEWS','nivel-kr','니벨아레나 공식 채널','NIVEL',true,3600,now()),
 ('OFFICIAL_NEWS','riftbound-en','Riot Games 리프트바운드 공지','RIFTBOUND',true,3600,now())
ON CONFLICT(provider,source_key) DO NOTHING;
