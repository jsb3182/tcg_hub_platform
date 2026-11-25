package kr.tcghub;

import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.time.Duration;
import java.time.Instant;
import java.util.Collections;
import java.util.Locale;
import java.util.Optional;
import java.util.Set;
import java.util.regex.Pattern;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;
import io.github.bucket4j.Bucket;
import jakarta.servlet.http.Cookie;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseCookie;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
class LocalAdmin {
    enum Mode { LOCAL_TOTP, CLOUDFLARE, DISABLED }
    private record Factor(long userId, String secretBase32) {}
    static final String COOKIE = "__Host-tcg_local_admin";
    static final String LOCAL_ORIGIN = "http://127.0.0.1:8080";
    private static final Duration LIFETIME = Duration.ofMinutes(15);
    private static final Pattern TOKEN = Pattern.compile("[A-Za-z0-9_-]{43}");
    private static final Set<String> PROXY_HEADERS = Set.of("forwarded", "via", "x-real-ip", "true-client-ip",
            "x-client-ip", "x-original-host", "x-original-url", "x-rewrite-url");
    private final Cache<String, Bucket> attempts = Caffeine.newBuilder().maximumSize(4096)
            .expireAfterAccess(Duration.ofMinutes(10)).build();
    private final AccessGate cloudflare;
    private final JdbcClient db;
    private final boolean localListener;

    LocalAdmin(AccessGate cloudflare, JdbcClient db, @Value("${tcg.public-origin}") String origin,
               @Value("${server.address:}") String bind, @Value("${server.forward-headers-strategy:}") String forwarding) {
        this.cloudflare = cloudflare;
        this.db = db;
        this.localListener = LOCAL_ORIGIN.equals(origin) && "127.0.0.1".equals(bind)
                && "none".equalsIgnoreCase(forwarding);
    }

    Mode mode(HttpServletRequest request) {
        if (cloudflare.configured()) return Mode.CLOUDFLARE;
        return directLocalRequest(request,"127.0.0.1:8080") ? Mode.LOCAL_TOTP : Mode.DISABLED;
    }

    boolean localEntryAlias(HttpServletRequest request) {
        return !cloudflare.configured() && directLocalRequest(request,"localhost:8080");
    }

    private boolean directLocalRequest(HttpServletRequest request, String host) {
        if (!localListener || !"http".equals(request.getScheme()) || request.getLocalPort() != 8080
                || !"127.0.0.1".equals(request.getLocalAddr()) || !"127.0.0.1".equals(request.getRemoteAddr())
                || !Collections.list(request.getHeaders("Host")).equals(java.util.List.of(host))) {
            return false;
        }
        for (String name : Collections.list(request.getHeaderNames())) {
            String header = name.toLowerCase(Locale.ROOT);
            if (header.startsWith("cf-") || header.startsWith("x-forwarded") || PROXY_HEADERS.contains(header)) {
                return false;
            }
        }
        return true;
    }

    boolean admits(HttpServletRequest request, String requiredEmail) {
        Mode selected = mode(request);
        if (selected == Mode.CLOUDFLARE) return cloudflare.admits(request);
        if (selected != Mode.LOCAL_TOTP) return false;
        return cookieToken(request).flatMap(token -> db.sql("""
                select u.email from local_admin_session s join app_user u on u.id=s.user_id
                where s.token_hash=? and s.expires_at>now() and u.enabled and u.role='ROLE_ADMIN'
                """).param(Accounts.hash(token)).query(String.class).optional())
                .filter(email -> requiredEmail == null || requiredEmail.equals(email)).isPresent();
    }

    @Transactional
    public String verify(HttpServletRequest request, String email, String code) {
        if (mode(request) != Mode.LOCAL_TOTP) throw denied();
        Bucket bucket = attempts.get(email, key -> Bucket.builder().addLimit(limit -> limit
                .capacity(5).refillGreedy(5, Duration.ofMinutes(5))).build());
        if (!bucket.tryConsume(1)) throw new ResponseStatusException(HttpStatus.TOO_MANY_REQUESTS);
        Factor factor = db.sql("""
                select f.user_id,f.secret_base32 from local_admin_factor f join app_user u on u.id=f.user_id
                where u.email=? and u.enabled and u.role='ROLE_ADMIN'
                """).param(email).query(Factor.class).optional().orElseThrow(LocalAdmin::denied);
        long accepted = matchedStep(factor.secretBase32(), code, Instant.now());
        if (accepted < 0) throw denied();
        // Holding the row lock through the session insert makes simultaneous verification and rotation safe.
        int changed = db.sql("""
                update local_admin_factor set last_step=?
                where user_id=? and secret_base32=? and (last_step is null or last_step<?)
                """).param(accepted).param(factor.userId()).param(factor.secretBase32()).param(accepted).update();
        if (changed != 1) throw denied();
        String token = Accounts.randomToken();
        db.sql("delete from local_admin_session where expires_at<=now()").update();
        db.sql("insert into local_admin_session(token_hash,user_id,expires_at) values(?,?,now()+? * interval '1 second')")
                .param(Accounts.hash(token)).param(factor.userId()).param(LIFETIME.toSeconds()).update();
        return token;
    }

    static long matchedStep(String base32, String code, Instant instant) {
        // The provisioning CLI generates exactly 160 bits, encoded as 32 RFC 4648 Base32 characters.
        byte[] key = new byte[20];
        int bits = 0, accumulator = 0, index = 0;
        for (char c : base32.toCharArray()) {
            int value = c <= 'Z' && c >= 'A' ? c - 'A' : c - '2' + 26;
            accumulator = (accumulator << 5) | value;
            bits += 5;
            if (bits >= 8) {
                bits -= 8;
                key[index++] = (byte)(accumulator >>> bits);
            }
        }
        try {
            Mac mac = Mac.getInstance("HmacSHA1");
            mac.init(new SecretKeySpec(key, "HmacSHA1"));
            long current = instant.getEpochSecond() / 30;
            byte[] supplied = code.getBytes(StandardCharsets.US_ASCII);
            for (long step = current + 1; step >= current - 1; step--) {
                byte[] result = mac.doFinal(ByteBuffer.allocate(8).putLong(step).array());
                int value = ByteBuffer.wrap(result, result[result.length-1] & 15, 4).getInt() & 0x7fff_ffff;
                String candidate = String.format(Locale.ROOT,"%06d", value % 1_000_000);
                if (MessageDigest.isEqual(candidate.getBytes(StandardCharsets.US_ASCII),supplied)) return step;
            }
            return -1;
        } catch (GeneralSecurityException impossible) { throw new IllegalStateException(impossible); }
    }

    void revoke(HttpServletRequest request) {
        cookieToken(request).ifPresent(token -> db.sql("delete from local_admin_session where token_hash=?")
                .param(Accounts.hash(token)).update());
    }

    void cookie(HttpServletResponse response, String token) {
        response.addHeader(HttpHeaders.SET_COOKIE, ResponseCookie.from(COOKIE, token).httpOnly(true).secure(true)
                .sameSite("Strict").path("/").maxAge(token.isEmpty() ? Duration.ZERO : LIFETIME).build().toString());
    }

    private Optional<String> cookieToken(HttpServletRequest request) {
        String value = null;
        if (request.getCookies() != null) for (Cookie cookie : request.getCookies()) {
            if (COOKIE.equals(cookie.getName())) {
                if (value != null || !TOKEN.matcher(cookie.getValue()).matches()) return Optional.empty();
                value = cookie.getValue();
            }
        }
        return Optional.ofNullable(value);
    }

    private static ResponseStatusException denied() { return new ResponseStatusException(HttpStatus.FORBIDDEN); }
}
