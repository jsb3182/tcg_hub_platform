package kr.tcghub.control;

import java.net.IDN;
import java.net.URI;
import java.net.URISyntaxException;
import java.util.Locale;
import java.util.regex.Pattern;

final class PublicSite {
    private static final Pattern DOMAIN = Pattern.compile(
            "(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\\.)+[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?");

    private PublicSite() {}

    static String root(String input) {
        if (input == null) return "";
        try {
            URI uri = new URI(input.trim());
            if (!"https".equalsIgnoreCase(uri.getScheme()) || uri.getRawAuthority() == null) return "";
            String host = uri.getRawAuthority();
            if (host.endsWith(":443")) host = host.substring(0, host.length() - 4);
            host = IDN.toASCII(host, IDN.USE_STD3_ASCII_RULES).toLowerCase(Locale.ROOT);
            if (host.endsWith(".")) host = host.substring(0, host.length() - 1);
            if (host.length() > 253 || !DOMAIN.matcher(host).matches() ||
                    host.endsWith(".localhost") || host.endsWith(".local") || host.endsWith(".internal") ||
                    host.equals("home.arpa") || host.endsWith(".home.arpa")) return "";
            return "https://" + host + "/";
        } catch (URISyntaxException | IllegalArgumentException ex) {
            return "";
        }
    }
}
