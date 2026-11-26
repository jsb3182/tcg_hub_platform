package kr.tcghub;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.*;

@RestController
class MapConfiguration {
    record PublicConfig(String kakaoMapKey) {}
    private final String key;
    MapConfiguration(@Value("${tcg.kakao-map-key:}") String key) { this.key=key.strip(); }
    @GetMapping("/api/v1/config")
    PublicConfig config() { return new PublicConfig(key); }

    String contentPolicy() {
        String script = key.isEmpty() ? "" : " https://dapi.kakao.com https://t1.daumcdn.net https://t1.kakaocdn.net";
        String maps = key.isEmpty() ? "" : " https://*.daumcdn.net https://*.kakaocdn.net https://*.daum.net";
        String printings = " https://www.onepiece-cardgame.kr https://en.onepiece-cardgame.com https://www.onepiece-cardgame.com"
                + " https://optcgapi.com https://www.optcgapi.com https://assets.tcgdex.net https://images.pokemontcg.io"
                + " https://cards.image.pokemonkorea.co.kr https://www.pokemon-card.com";
        return "default-src 'self'; script-src 'self'" + script + "; connect-src 'self'" + script
                + "; img-src 'self' data: blob: https://tile.openstreetmap.org" + maps + printings
                + "; style-src 'self' 'unsafe-inline'; object-src 'none'; frame-ancestors 'none'; base-uri 'self'"
                + (key.isEmpty() ? "" : "; upgrade-insecure-requests");
    }
}
