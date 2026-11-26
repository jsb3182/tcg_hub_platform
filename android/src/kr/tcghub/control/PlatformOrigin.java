package kr.tcghub.control;

import java.net.URI;
import java.net.URISyntaxException;

/** The configured origin is native state. A document cannot promote a different host. */
final class PlatformOrigin {
    static final String LOCAL = "http://127.0.0.1:8080/";
    final String root;

    PlatformOrigin(String selected) {
        root = LOCAL.equals(selected) ? LOCAL : PublicSite.root(selected);
        if (root.isEmpty()) throw new IllegalArgumentException("Missing platform origin");
    }

    boolean owns(String address) {
        try {
            URI uri = new URI(address);
            URI base = new URI(root);
            int port = uri.getPort() == -1 && "https".equalsIgnoreCase(uri.getScheme()) ? 443 : uri.getPort();
            return uri.getRawUserInfo() == null && base.getScheme().equalsIgnoreCase(uri.getScheme())
                    && base.getHost().equalsIgnoreCase(uri.getHost())
                    && (LOCAL.equals(root) ? port == 8080 : port == 443);
        } catch (URISyntaxException | IllegalArgumentException e) {
            return false;
        }
    }

    boolean adminPage(String address) {
        if (!owns(address)) return false;
        String path = URI.create(address).getPath();
        return path.equals("/admin") || path.startsWith("/admin/");
    }

    boolean resource(String address) {
        if (owns(address)) return true;
        try {
            URI u = new URI(address);
            if (!"https".equalsIgnoreCase(u.getScheme()) || u.getRawUserInfo() != null
                    || (u.getPort() != -1 && u.getPort() != 443) || u.getHost() == null
                    || !u.normalize().equals(u) || !u.getPath().equals(u.getRawPath())) return false;
            String path = u.getPath();
            String host = u.getHost().toLowerCase(java.util.Locale.ROOT);
            // The official Kakao SDK fetches its own subresources from a rotating CDN.
            if (host.endsWith(".kakaocdn.net")) return true;
            switch (host) {
                case "tile.openstreetmap.org": return path.matches("/[0-9]{1,2}/[0-9]{1,9}/[0-9]{1,9}\\.png");
                case "dapi.kakao.com": return path.equals("/v2/maps/sdk.js");
                case "t1.daumcdn.net": return path.startsWith("/mapjsapi/") || path.startsWith("/localimg/") || path.startsWith("/map/");
                case "assets.tcgdex.net": case "images.pokemontcg.io": return true;
                case "cards.image.pokemonkorea.co.kr": return path.startsWith("/data/wmimages/");
                case "www.pokemon-card.com": return path.startsWith("/assets/images/card_images/large/");
                case "www.onepiece-cardgame.kr": return path.equals("/fileDownload");
                case "en.onepiece-cardgame.com": case "www.onepiece-cardgame.com": return path.startsWith("/images/cardlist/card/");
                case "optcgapi.com": case "www.optcgapi.com": return path.startsWith("/media/static/Card_Images/");
                default: return host.matches("map[0-4]\\.daumcdn\\.net") && path.startsWith("/map_");
            }
        } catch (URISyntaxException e) { return false; }
    }
}
