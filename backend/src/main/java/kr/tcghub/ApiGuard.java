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
        boolean login = req.getServletPath().equals("/api/v1/auth/login");
        int limit = login ? 10 : 180;
        var bucket = buckets.get((login ? "login/" : "api/") + client,
                key -> Bucket.builder().addLimit(l -> l.capacity(limit).refillGreedy(limit, Duration.ofMinutes(1))).build());
        if (!bucket.tryConsume(1)) {
            res.setHeader("Retry-After","60");
            res.setStatus(429);
            return;
        }
        if ("GET".equals(req.getMethod()) && req.getServletPath().matches("/api/v1/(games|packs|cards(/[0-9]+)?)")) {
            res.setHeader("Cache-Control", "public, max-age=0, must-revalidate");
        }
        chain.doFilter(req,res);
    }
}
