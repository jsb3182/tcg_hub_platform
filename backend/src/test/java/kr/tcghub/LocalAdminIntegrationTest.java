package kr.tcghub;

import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.List;
import java.util.Locale;
import java.util.UUID;
import java.util.concurrent.Callable;
import java.util.concurrent.Executors;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import jakarta.servlet.http.Cookie;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.autoconfigure.web.servlet.MockMvcPrint;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;
import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest(properties={"tcg.public-origin=http://127.0.0.1:8080", "server.address=127.0.0.1",
        "tcg.cf-audience=", "tcg.cf-team-domain="})
@AutoConfigureMockMvc(print=MockMvcPrint.NONE)
@EnabledIfEnvironmentVariable(named="TCG_TEST_DB",matches="1")
class LocalAdminIntegrationTest {
    // Public RFC 6238 Appendix B input, used solely in the disposable database.
    private static final String VECTOR = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ";
    private static final String ORIGIN = "http://127.0.0.1:8080";
    private static final String VERIFY = "/api/v1/auth/local-admin";
    private static final String STATUS = "/api/v1/admin/status";
    @Autowired MockMvc http;
    @Autowired JdbcClient db;
    @Autowired Tokens tokens;
    long id;
    String bearer;

    @BeforeEach void enrollFixture() {
        String email = UUID.randomUUID()+"@example.invalid";
        id = db.sql("insert into app_user(email,password_hash,role) values(?,'test-only','ROLE_ADMIN') returning id")
                .param(email).query(Long.class).single();
        db.sql("insert into local_admin_factor(user_id,secret_base32) values(?,?)").param(id).param(VECTOR).update();
        bearer = "Bearer "+tokens.issue(email,"ROLE_ADMIN");
    }

    @AfterEach void cleanup() {
        db.sql("delete from app_user where id=?").param(id).update();
    }

    private MockHttpServletRequestBuilder local(MockHttpServletRequestBuilder req) {
        return req.header("Host","127.0.0.1:8080").with(request -> {
            request.setLocalAddr("127.0.0.1"); request.setRemoteAddr("127.0.0.1"); request.setLocalPort(8080);
            return request;
        });
    }

    private String otp() throws Exception {
        Mac mac = Mac.getInstance("HmacSHA1");
        mac.init(new SecretKeySpec("12345678901234567890".getBytes(StandardCharsets.US_ASCII),"HmacSHA1"));
        byte[] result = mac.doFinal(ByteBuffer.allocate(8).putLong(Instant.now().getEpochSecond()/30).array());
        int offset = result[19] & 15;
        return String.format(Locale.ROOT,"%06d",(ByteBuffer.wrap(result).getInt(offset)&Integer.MAX_VALUE)%1000000);
    }

    private MockHttpServletRequestBuilder verify(String code) {
        return local(post(VERIFY).servletPath(VERIFY)).header("Authorization",bearer).header("Origin",ORIGIN)
                .header("X-TCG-Request","1").contentType("application/json").content("{\"code\":\""+code+"\"}");
    }

    private Cookie session() throws Exception {
        return http.perform(verify(otp())).andExpect(status().isNoContent()).andReturn().getResponse().getCookie(LocalAdmin.COOKIE);
    }

    @Test void localCookieGatesShellAndRequiresMatchingBearerForDataUntilLogout() throws Exception {
        http.perform(local(get("/api/v1/auth/admin-mode"))).andExpect(jsonPath("$.mode").value("LOCAL_TOTP"));
        http.perform(local(get("/admin"))).andExpect(redirectedUrl("/login?next=/admin"));
        http.perform(local(get(STATUS)).header("Authorization",bearer)).andExpect(status().isForbidden());
        var response = http.perform(verify(otp())).andExpect(status().isNoContent()).andReturn().getResponse();
        Cookie factor = response.getCookie(LocalAdmin.COOKIE);
        assertNotNull(factor);
        assertTrue(factor.isHttpOnly() && factor.getSecure());
        assertNull(factor.getDomain());
        assertEquals("/",factor.getPath());
        assertTrue(response.getHeader("Set-Cookie").contains("SameSite=Strict"));
        http.perform(local(get("/admin/")).cookie(factor)).andExpect(forwardedUrl("/index.html"));
        http.perform(local(get(STATUS)).cookie(factor)).andExpect(status().isUnauthorized());
        http.perform(local(get(STATUS)).cookie(factor).header("Authorization",bearer)).andExpect(status().isOk());
        http.perform(local(get(STATUS)).cookie(factor).header("Authorization",
                "Bearer "+tokens.issue("different@example.invalid","ROLE_ADMIN"))).andExpect(status().isForbidden());
        String logout = "/api/v1/auth/logout";
        http.perform(local(post(logout).servletPath(logout)).header("Origin",ORIGIN).header("X-TCG-Request","1").cookie(factor))
                .andExpect(status().isNoContent());
        http.perform(local(get("/admin")).cookie(factor)).andExpect(redirectedUrl("/login?next=/admin"));
    }

    @Test void twoConcurrentSubmissionsOfSameStepCanIssueOnlyOneSession() throws Exception {
        String same = otp();
        Callable<Integer> call = () -> http.perform(verify(same)).andReturn().getResponse().getStatus();
        var pool = Executors.newFixedThreadPool(2);
        try {
            var results = pool.invokeAll(List.of(call,call));
            assertEquals(List.of(204,403),java.util.stream.Stream.of(results.get(0).get(),results.get(1).get()).sorted().toList());
            assertEquals(1,db.sql("select count(*) from local_admin_session where user_id=?").param(id).query(Integer.class).single());
        } finally { pool.shutdownNow(); }
    }

    @Test void proxyHeadersHostAndAddressCannotSelectLocalModeOrUseExistingSession() throws Exception {
        Cookie factor = session();
        String path = "/api/v1/auth/admin-mode";
        for (String proxy : List.of("Forwarded","X-Forwarded-For","CF-Connecting-IP","CF-Ray","Via","X-Real-IP")) {
            http.perform(local(get(path)).header(proxy,"test")).andExpect(jsonPath("$.mode").value("DISABLED"));
            http.perform(local(get(STATUS)).header(proxy,"test").header("Authorization",bearer).cookie(factor)).andExpect(status().isForbidden());
        }
        http.perform(local(get(path)).with(req -> { req.removeHeader("Host"); req.addHeader("Host","localhost:8080"); return req; }))
                .andExpect(jsonPath("$.mode").value("DISABLED"));
        http.perform(local(get(path)).with(req -> { req.setRemoteAddr("192.0.2.1"); return req; }))
                .andExpect(jsonPath("$.mode").value("DISABLED"));
        http.perform(local(get(path)).with(req -> { req.setLocalAddr("192.0.2.2"); return req; }))
                .andExpect(jsonPath("$.mode").value("DISABLED"));
    }

    @Test void deactivationRevocationExpiryAndRotationTakeEffectOnTheNextRequest() throws Exception {
        Cookie factor = session();
        db.sql("update app_user set enabled=false where id=?").param(id).update();
        http.perform(local(get(STATUS)).header("Authorization",bearer).cookie(factor)).andExpect(status().isForbidden());
        db.sql("update app_user set enabled=true where id=?").param(id).update();
        db.sql("update local_admin_session set expires_at=now()-interval '1 second' where user_id=?").param(id).update();
        http.perform(local(get(STATUS)).header("Authorization",bearer).cookie(factor)).andExpect(status().isForbidden());
        db.sql("delete from local_admin_factor where user_id=?").param(id).update();
        assertEquals(0,db.sql("select count(*) from local_admin_session where user_id=?").param(id).query(Integer.class).single());
        http.perform(verify(otp())).andExpect(status().isForbidden());
    }

    @Test void perAccountLimitAppliesToFailedAttempts() throws Exception {
        db.sql("delete from local_admin_factor where user_id=?").param(id).update();
        for (int i=0;i<5;i++) http.perform(verify("000000")).andExpect(status().isForbidden());
        http.perform(verify("000000")).andExpect(status().isTooManyRequests());
    }

    @Test void interoperatesWithRfc6238IncludingLeadingZerosAndClockDrift() {
        assertEquals(1,LocalAdmin.matchedStep(VECTOR,"287082",Instant.ofEpochSecond(59)));
        long step = 1111111109L / 30;
        assertEquals(step,LocalAdmin.matchedStep(VECTOR,"081804",Instant.ofEpochSecond(1111111109L+30)));
        assertEquals(-1,LocalAdmin.matchedStep(VECTOR,"081804",Instant.ofEpochSecond(1111111109L+60)));
    }
}
