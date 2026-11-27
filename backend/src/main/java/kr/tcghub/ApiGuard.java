package kr.tcghub;

import java.io.IOException;
import java.time.Duration;
import java.util.Set;
import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;
import io.github.bucket4j.Bucket;
import jakarta.servlet.*;
import jakarta.servlet.http.*;
import org.springframework.web.filter.OncePerRequestFilter;

/** Stateless API. Browser writes require the configured origin and a non-simple header. */
class ApiGuard extends OncePerRequestFilter {
    private final String origin;
    private final Cache<String, Bucket> buckets = Caffeine.newBuilder().maximumSize(8192)
            .expireAfterAccess(Duration.ofMinutes(10)).build();
    // Hold the total volume of public BCrypt work down even when requests arrive from different IPs.
    private final Bucket registrationBudget = budget(12, Duration.ofMinutes(1));

    ApiGuard(String origin) { this.origin = origin; }

    @Override protected boolean shouldNotFilter(HttpServletRequest request) {
        return !request.getServletPath().startsWith("/api/");
    }

    @Override protected void doFilterInternal(HttpServletRequest req, HttpServletResponse res, FilterChain chain)
            throws IOException, ServletException {
        if (!Set.of("GET","HEAD","OPTIONS").contains(req.getMethod())
                && (!origin.equals(req.getHeader("Origin")) || !"1".equals(req.getHeader("X-TCG-Request")))) {
            res.setStatus(403);
            return;
        }
        String client = req.getRemoteAddr();
        // The listener is bound to loopback and Cloudflare sets this header on the tunnel.
        String forwarded = req.getHeader("CF-Connecting-IP");
        if ("127.0.0.1".equals(client) && forwarded != null && forwarded.matches("[a-fA-F0-9:.]{2,45}")) {
            client = forwarded;
        }
        String path = req.getServletPath();
        if (path.equals("/api/v1/auth/register") && "POST".equals(req.getMethod())) {
            Bucket clientBudget = buckets.get("register/" + client, key -> budget(5, Duration.ofMinutes(10)));
            if (!consume(clientBudget, res) || !consume(registrationBudget, res)) return;
        } else {
            boolean login = path.equals("/api/v1/auth/login");
            Bucket bucket = buckets.get((login ? "login/" : "api/") + client,
                    key -> budget(login ? 10 : 180, Duration.ofMinutes(1)));
            if (!consume(bucket, res)) return;
        }
        if ("GET".equals(req.getMethod()) && req.getServletPath().matches("/api/v1/(games|release-calendar|packs|cards(/[0-9]+)?)")) {
            res.setHeader("Cache-Control", "public, max-age=0, must-revalidate");
        }
        chain.doFilter(req,res);
    }

    private static Bucket budget(int tokens, Duration period) {
        return Bucket.builder().addLimit(limit -> limit.capacity(tokens).refillGreedy(tokens, period)).build();
    }

    private static boolean consume(Bucket bucket, HttpServletResponse response) {
        var result = bucket.tryConsumeAndReturnRemaining(1);
        if (result.isConsumed()) return true;
        long seconds = (result.getNanosToWaitForRefill() + 999_999_999L) / 1_000_000_000L;
        response.setHeader("Retry-After", Long.toString(Math.max(1L, seconds)));
        response.setStatus(429);
        return false;
    }
}
