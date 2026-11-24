package kr.tcghub;

import jakarta.servlet.http.HttpServletRequest;
import java.time.Duration;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.security.oauth2.core.*;
import org.springframework.security.oauth2.jwt.*;
import org.springframework.stereotype.Component;

@Component
class AccessGate {
    private final NimbusJwtDecoder decoder;

    AccessGate(@Value("${tcg.cf-team-domain}") String team, @Value("${tcg.cf-audience}") String audience,
               RestTemplateBuilder http) {
        if (team.isBlank() && audience.isBlank()) {
            decoder = null;
            return;
        }
        if (!team.matches("[a-zA-Z0-9-]+\\.cloudflareaccess\\.com") || audience.isBlank()) {
            throw new IllegalArgumentException("Set CF_TEAM_DOMAIN and CF_AUDIENCE together");
        }
        String issuer = "https://" + team;
        decoder = NimbusJwtDecoder.withJwkSetUri(issuer + "/cdn-cgi/access/certs")
                .restOperations(http.connectTimeout(Duration.ofSeconds(4)).readTimeout(Duration.ofSeconds(5)).build())
                .build();
        OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
                jwt.getAudience() != null && jwt.getAudience().contains(audience) && jwt.getExpiresAt() != null
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(new OAuth2Error("invalid_token"));
        decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(JwtValidators.createDefaultWithIssuer(issuer), audienceValidator));
    }

    boolean configured() { return decoder != null; }

    boolean admits(HttpServletRequest request) {
        String assertion = request.getHeader("Cf-Access-Jwt-Assertion");
        if (decoder == null || assertion == null || assertion.isBlank()) return false;
        try {
            decoder.decode(assertion);
            return true;
        } catch (JwtException invalid) {
            return false;
        }
    }
}
