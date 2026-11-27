INSERT INTO feed_source(provider,source_key,game_code,label,auto_publish,interval_seconds,next_fetch_at,policy_note,enabled)
VALUES ('POKEWALLET','POKEMON','POKEMON','PokéWallet · 포켓몬 인쇄본·시세',true,86400,now(),'POKEWALLET_API_KEY 미설정',false);

UPDATE feed_source SET interval_seconds=604800 WHERE provider='WIKI_INDEX';
