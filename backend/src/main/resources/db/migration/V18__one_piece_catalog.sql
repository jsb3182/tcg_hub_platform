INSERT INTO game(code,name) VALUES ('ONEPIECE','원피스 카드게임');
INSERT INTO feed_source(provider,source_key,label,game_code,auto_publish,interval_seconds,next_fetch_at) VALUES
 ('CATALOG','ONEPIECE','원피스 카드게임 · OPTCG API / Koala Kollect / 반다이남코코리아','ONEPIECE',true,86400,now()),
 ('OFFICIAL_NEWS','onepiece-kr','반다이남코코리아 원피스 공식 공지','ONEPIECE',true,3600,now()),
 ('X','ONEPIECE_tcg_KR','원피스 카드게임 한국 공식 X','ONEPIECE',false,3600,now());
INSERT INTO deck_rule(game_code,format,version,max_copies_per_card,details) VALUES
 ('ONEPIECE','CONSTRUCTED',2,4,'{"source":"https://www.onepiece-cardgame.kr/rules.do"}');
INSERT INTO deck_section_rule(game_code,format,rule_version,section,min_cards,max_cards) VALUES
 ('ONEPIECE','CONSTRUCTED',2,'LEADER',1,1),
 ('ONEPIECE','CONSTRUCTED',2,'MAIN',50,50),
 ('ONEPIECE','CONSTRUCTED',2,'DON',10,10);
