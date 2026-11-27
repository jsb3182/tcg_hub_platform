package kr.tcghub;

import org.springframework.jdbc.core.simple.JdbcClient;

final class CachedArtwork {
    private CachedArtwork() {}

    static String link(JdbcClient db, long card, String source, char digestDigit) {
        String key = "cards/" + String.valueOf(digestDigit).repeat(64) + ".webp";
        db.sql("""
            with cached as (
                insert into catalog_art_file(game_code,source_url,storage_key)
                select game_code,?,? from card where id=?
                on conflict(source_url) do update set storage_key=excluded.storage_key returning id)
            insert into catalog_art_card(card_id,file_id) select ?,id from cached on conflict do nothing
            """).param(source).param(key).param(card).param(card).update();
        return "/media/" + key;
    }
}
