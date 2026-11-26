package kr.tcghub;

import java.time.Instant;
import java.util.Date;
import com.nimbusds.jose.JOSEException;
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.gen.RSAKeyGenerator;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.web.client.RestTemplateCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import static org.springframework.test.web.client.ExpectedCount.manyTimes;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

@TestConfiguration(proxyBeanMethods=false)
class TestAccessProvider {
    static final String ISSUER = "https://tcg-test-fixture.cloudflareaccess.com";
    static final String ASSERTION = "Cf-Access-Jwt-Assertion";

    @Bean RSAKey testKey() throws JOSEException {
        return new RSAKeyGenerator(2048).keyID("fixture").generate();
    }

    @Bean RestTemplateCustomizer publicKeys(RSAKey key) {
        return client -> MockRestServiceServer.bindTo(client).build()
                .expect(manyTimes(),requestTo(ISSUER + "/cdn-cgi/access/certs"))
                .andRespond(withSuccess(new JWKSet(key.toPublicJWK()).toString(), MediaType.APPLICATION_JSON));
    }

    static String assertion(RSAKey signingKey, String issuer, String audience, Instant expiry) throws JOSEException {
        var claims = new JWTClaimsSet.Builder().issuer(issuer).audience(audience).subject("test-operator");
        if (expiry!=null) claims.expirationTime(Date.from(expiry));
        var signed = new SignedJWT(new JWSHeader.Builder(JWSAlgorithm.RS256).keyID(signingKey.getKeyID()).build(),claims.build());
        signed.sign(new RSASSASigner(signingKey));
        return signed.serialize();
    }
}
