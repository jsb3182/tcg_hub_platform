package kr.tcghub;

import java.time.Duration;
import java.time.Instant;
import java.util.Base64;
import javax.crypto.spec.SecretKeySpec;
import com.nimbusds.jose.jwk.source.ImmutableSecret;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.security.oauth2.jose.jws.MacAlgorithm;
import org.springframework.security.oauth2.jwt.*;

@Component
class Tokens {
    static final String ISSUER = "tcg-hub";
    static final Duration ACCESS_LIFETIME = Duration.ofMinutes(15);
    final NimbusJwtDecoder decoder;
    private final JwtEncoder encoder;

    Tokens(@Value("${tcg.jwt-secret}") String secret) {
        byte[] bytes = Base64.getDecoder().decode(secret);
        if (bytes.length < 32) throw new IllegalArgumentException("JWT_SECRET requires at least 32 decoded bytes");
        var key = new SecretKeySpec(bytes, "HmacSHA256");
        decoder = NimbusJwtDecoder.withSecretKey(key).macAlgorithm(MacAlgorithm.HS256).build();
        decoder.setJwtValidator(JwtValidators.createDefaultWithIssuer(ISSUER));
        encoder = new NimbusJwtEncoder(new ImmutableSecret<>(key));
    }

    String issue(String email, String role) {
        Instant now = Instant.now();
        var claims = JwtClaimsSet.builder().issuer(ISSUER).subject(email).issuedAt(now)
                .expiresAt(now.plus(ACCESS_LIFETIME)).claim("role", role).build();
        return encoder.encode(JwtEncoderParameters.from(JwsHeader.with(MacAlgorithm.HS256).build(), claims))
                .getTokenValue();
    }
}
