package kr.tcghub;

import java.time.Instant;
import java.util.Date;
import java.util.UUID;
import com.nimbusds.jose.*;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jose.jwk.*;
import com.nimbusds.jose.jwk.gen.RSAKeyGenerator;
import com.nimbusds.jwt.*;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.*;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.web.client.RestTemplateCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;
import org.springframework.transaction.annotation.Transactional;
import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.client.ExpectedCount.manyTimes;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest(properties={"tcg.cf-team-domain=tcg-test-fixture.cloudflareaccess.com","tcg.cf-audience=test-ops"})
@AutoConfigureMockMvc
@Transactional
@EnabledIfEnvironmentVariable(named="TCG_TEST_DB",matches="1")
class OperationsIntegrationTest {
    @Autowired MockMvc http;
    @Autowired JdbcClient db;
    @Autowired Tokens tokens;
    @Value("${tcg.public-origin}") String origin;
    static final String ISSUER = "https://tcg-test-fixture.cloudflareaccess.com";
    static final String ASSERTION = "Cf-Access-Jwt-Assertion";
    @TestConfiguration(proxyBeanMethods=false)
    static class TestIdentityProvider {
        @Bean RSAKey testKey() throws JOSEException {
            return new RSAKeyGenerator(2048).keyID("fixture").generate();
        }
        @Bean RestTemplateCustomizer publicKeys(RSAKey key) {
            return client -> MockRestServiceServer.bindTo(client).build()
                    .expect(manyTimes(),requestTo(ISSUER + "/cdn-cgi/access/certs"))
                    .andRespond(withSuccess(new JWKSet(key.toPublicJWK()).toString(), MediaType.APPLICATION_JSON));
        }
    }
    @Autowired RSAKey key;
    String access;
    String admin;
    long source;
    long item;

    private String assertion(RSAKey signingKey, String issuer, String audience, Instant expiry) throws JOSEException {
        var claims = new JWTClaimsSet.Builder().issuer(issuer).audience(audience).subject("test-operator");
        if (expiry!=null) claims.expirationTime(Date.from(expiry));
        var signed = new SignedJWT(new JWSHeader.Builder(JWSAlgorithm.RS256).keyID(signingKey.getKeyID()).build(),claims.build());
        signed.sign(new RSASSASigner(signingKey));
        return signed.serialize();
    }

    @BeforeEach void setup() throws JOSEException {
        access = assertion(key, ISSUER, "test-ops", Instant.now().plusSeconds(300));
        String email = UUID.randomUUID() + "@example.invalid";
        db.sql("insert into app_user(email,password_hash,role) values(?,'unused','ROLE_ADMIN')").param(email).update();
        admin = tokens.issue(email,"ROLE_ADMIN");
        source = db.sql("""
            insert into feed_source(provider,source_key,game_code,label) values('TEST',?,'NIVEL','테스트') returning id
            """).param(UUID.randomUUID().toString()).query(Long.class).single();
        item = db.sql("""
            insert into feed_item(source_id,external_id,source_url,payload) values(?,'1','https://example.invalid/news',
                '{"title":"검수 테스트","kind":"NEWS"}') returning id
            """).param(source).query(Long.class).single();
    }

    private MockHttpServletRequestBuilder command(String path) {
        String fullPath="/api/v1/admin"+path;
        return post(fullPath).servletPath(fullPath).header("Authorization","Bearer "+admin)
                .header(ASSERTION,access)
                .header("Origin",origin).header("X-TCG-Request","1").contentType("application/json");
    }

    @Test void gatewayAndRoleRequiredThenControlsReachDatabase() throws Exception {
        var snapshot = get("/api/v1/admin/operations").header("Authorization","Bearer "+admin);
        http.perform(snapshot).andExpect(status().isForbidden());
        http.perform(get("/api/v1/admin/operations").header(ASSERTION,access)
                .header("Authorization","Bearer "+tokens.issue("reader@example.invalid","ROLE_USER")))
                .andExpect(status().isForbidden());
        http.perform(snapshot.header(ASSERTION,access)).andExpect(status().isOk()).andExpect(jsonPath("$.sources").isArray())
                .andExpect(jsonPath("$.cardCounts.NIVEL").exists()).andExpect(jsonPath("$.diskTotalBytes").isNumber());
        http.perform(command("/sources/"+source+"/enabled").content("{\"enabled\":false}")).andExpect(status().isNoContent());
        http.perform(command("/sources/"+source+"/run")).andExpect(status().isConflict());
        http.perform(command("/sources/"+source+"/enabled").content("{\"enabled\":true}")).andExpect(status().isNoContent());
        http.perform(command("/sources/"+source+"/run")).andExpect(status().isNoContent());
        assertTrue(db.sql("select requested_at is not null from feed_source where id=?").param(source).query(Boolean.class).single());
        http.perform(command("/worker/restart")).andExpect(status().isAccepted());
        assertTrue(db.sql("select restart_requested_at is not null from worker_heartbeat where id='tcg-worker'").query(Boolean.class).single());
    }

    @Test void moderationPublishesOnlyApprovedNews() throws Exception {
        db.sql("update feed_source set game_code=null where id=?").param(source).update();
        long before = newsCount();
        http.perform(get("/api/v1/admin/review").header("Authorization","Bearer "+admin).header(ASSERTION,access))
                .andExpect(status().isOk());
        http.perform(command("/review/"+item+"/decision").content("{\"status\":\"PUBLISHED\",\"gameCode\":\"NIVEL\"}"))
                .andExpect(status().isNoContent());
        assertEquals(before+1,newsCount());
        http.perform(command("/review/"+item+"/decision").content("{\"status\":\"REJECTED\"}")).andExpect(status().isConflict());
        assertEquals(1,db.sql("select count(*) from operator_action where action='REVIEW_PUBLISHED' and target_id=?")
                .param(item).query(Integer.class).single());
    }

    @Test void accessAssertionMustMatchThePublishedKeyIssuerAudienceAndExpiry() throws Exception {
        var expires = Instant.now().plusSeconds(300);
        var other = new RSAKeyGenerator(2048).keyID(key.getKeyID()).generate();
        for (String invalid : new String[]{assertion(other,ISSUER,"test-ops",expires),
                assertion(key,"https://example.invalid","test-ops",expires), assertion(key,ISSUER,"other-app",expires),
                assertion(key,ISSUER,"test-ops",Instant.now().minusSeconds(300)), assertion(key,ISSUER,"test-ops",null)}) {
            http.perform(get("/api/v1/admin/operations").header("Authorization","Bearer "+admin).header(ASSERTION,invalid))
                    .andExpect(status().isForbidden());
        }
        http.perform(get("/admin").header(ASSERTION,access)).andExpect(forwardedUrl("/index.html"));
    }

    private long newsCount() throws Exception {
        var response=http.perform(get("/api/v1/news").param("game","NIVEL"))
                .andExpect(status().isOk()).andReturn().getResponse().getContentAsString();
        return new com.fasterxml.jackson.databind.ObjectMapper().readTree(response).get("total").asLong();
    }
}
