package kr.tcghub;

import java.util.*;
import java.util.concurrent.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;
import org.springframework.transaction.annotation.Transactional;
import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
@EnabledIfEnvironmentVariable(named="TCG_TEST_DB", matches="1")
class RegistrationIntegrationTest {
    static final String REGISTER = "/api/v1/auth/register";
    static final String REFRESH = "/api/v1/auth/refresh";
    static final String COOKIE = "__Secure-tcg_refresh";
    @Autowired MockMvc api;
    @Autowired ObjectMapper json;
    @Autowired JdbcClient db;
    @Value("${tcg.public-origin}") String origin;

    private MockHttpServletRequestBuilder write(MockHttpServletRequestBuilder request, Object body) throws Exception {
        return request.header("Origin", origin).header("X-TCG-Request", "1").contentType(MediaType.APPLICATION_JSON)
                .content(json.writeValueAsBytes(body));
    }

    private MockHttpServletRequestBuilder register(String client, Object input) throws Exception {
        return write(post(REGISTER).servletPath(REGISTER), input).with(req -> {req.setRemoteAddr(client); return req;});
    }

    private String email() { return UUID.randomUUID() + "@example.invalid"; }

    @Test @Transactional void memberCanImmediatelyUseBinderAndDeckAndRotateTheirSession() throws Exception {
        String email = email();
        String password = "🎴".repeat(18); // Exactly 72 UTF-8 bytes.
        var input = Map.of("email", " " + email.toUpperCase(Locale.ROOT) + " ", "password", password, "role", "ROLE_ADMIN");
        var response = api.perform(register("192.0.2.11", input)).andExpect(status().isCreated())
                .andExpect(jsonPath("$.role").value("ROLE_USER")).andExpect(jsonPath("$.email").value(email))
                .andExpect(header().string("Cache-Control", org.hamcrest.Matchers.containsString("no-store")))
                .andReturn().getResponse();
        var body = json.readTree(response.getContentAsByteArray());
        assertEquals(3, body.size());
        var refresh = response.getCookie(COOKIE);
        assertNotNull(refresh);
        assertTrue(refresh.isHttpOnly() && refresh.getSecure());
        assertEquals("/api/v1/auth", refresh.getPath());
        assertNull(refresh.getDomain());
        assertTrue(response.getHeader("Set-Cookie").contains("SameSite=Strict"));
        String hash = db.sql("select password_hash from app_user where email=? and role='ROLE_USER' and enabled")
                .param(email).query(String.class).single();
        assertTrue(new BCryptPasswordEncoder().matches(password, hash));
        String auth = "Bearer " + body.get("accessToken").asText();
        api.perform(get("/api/v1/admin/status").header("Authorization", auth)).andExpect(status().isForbidden());
        long card = db.sql("insert into card(game_code,name,status) values('YUGIOH','가입 테스트','PUBLISHED') returning id")
                .query(Long.class).single();
        String binder = "/api/v1/me/binder/" + card;
        api.perform(write(put(binder).servletPath(binder), new BinderApi.Quantity(1, 0)).header("Authorization", auth))
                .andExpect(status().isOk());
        String decks = "/api/v1/me/decks";
        var draft = new DeckApi.Save("첫 덱", "YUGIOH", "DRAFT", 0, false, List.of(new DeckRules.Line(card, "MAIN", 1)));
        api.perform(write(post(decks).servletPath(decks), draft).header("Authorization", auth)).andExpect(status().isCreated());
        var renewed = api.perform(post(REFRESH).servletPath(REFRESH).cookie(refresh).header("Origin", origin)
                        .header("X-TCG-Request", "1")).andExpect(status().isOk()).andReturn().getResponse();
        assertNotEquals(refresh.getValue(), Objects.requireNonNull(renewed.getCookie(COOKIE)).getValue());
        String renewedAuth = "Bearer " + json.readTree(renewed.getContentAsByteArray()).get("accessToken").asText();
        api.perform(get(binder).header("Authorization", renewedAuth)).andExpect(jsonPath("$.quantity").value(1));
        api.perform(get(decks).header("Authorization", renewedAuth)).andExpect(jsonPath("$.total").value(1));
    }

    @Test @Transactional void duplicateCannotChangeOrOpenAnExistingAdminAccount() throws Exception {
        String email = email();
        db.sql("insert into app_user(email,password_hash,role,enabled) values(?,'original-hash','ROLE_ADMIN',false)")
                .param(email).update();
        api.perform(register("192.0.2.12", Map.of("email", " " + email.toUpperCase(Locale.ROOT), "password", "synthetic-12")))
                .andExpect(status().isConflict()).andExpect(cookie().doesNotExist(COOKIE));
        assertEquals(1, db.sql("select count(*) from app_user where email=? and password_hash='original-hash' and role='ROLE_ADMIN' and not enabled")
                .param(email).query(Integer.class).single());
        assertEquals(0, sessionCount(email));
    }

    @Test @Transactional void invalidInputAndCrossOriginRequestsCreateNoAccount() throws Exception {
        String email = email();
        for (String invalid : List.of("🎴".repeat(11), "한".repeat(25), " ".repeat(12))) {
            api.perform(register("192.0.2.13", Map.of("email", email, "password", invalid)))
                    .andExpect(status().isBadRequest()).andExpect(cookie().doesNotExist(COOKIE));
        }
        api.perform(register("192.0.2.13", Map.of("email", "invalid", "password", "synthetic-12")))
                .andExpect(status().isBadRequest());
        var valid = json.writeValueAsBytes(Map.of("email", email, "password", "synthetic-12"));
        api.perform(post(REGISTER).servletPath(REGISTER).header("Origin", origin).contentType(MediaType.APPLICATION_JSON).content(valid))
                .andExpect(status().isForbidden());
        api.perform(post(REGISTER).servletPath(REGISTER).header("Origin", "https://other.invalid").header("X-TCG-Request", "1")
                .contentType(MediaType.APPLICATION_JSON).content(valid)).andExpect(status().isForbidden());
        assertEquals(0, db.sql("select count(*) from app_user where email=?").param(email).query(Integer.class).single());
    }

    @Test void concurrentRegistrationOfCanonicalEmailCreatesOneAccountAndSession() throws Exception {
        String email = email();
        var inputs = List.of(Map.of("email", email, "password", "first-synthetic"),
                Map.of("email", email.toUpperCase(Locale.ROOT), "password", "second-synthetic"));
        var start = new CountDownLatch(1);
        var pool = Executors.newFixedThreadPool(2);
        try {
            var results = new ArrayList<Future<MockHttpServletResponse>>();
            for (var input : inputs) {
                results.add(pool.submit(() -> {
                    start.await();
                    return api.perform(register("192.0.2.14", input)).andReturn().getResponse();
                }));
            }
            start.countDown();
            String hash;
            var statuses = new ArrayList<Integer>();
            for (int i = 0; i < results.size(); i++) {
                var response = results.get(i).get(20, TimeUnit.SECONDS);
                statuses.add(response.getStatus());
                if (response.getStatus() == 201) {
                    hash = db.sql("select password_hash from app_user where email=?").param(email).query(String.class).single();
                    assertTrue(new BCryptPasswordEncoder().matches(inputs.get(i).get("password"), hash));
                } else assertNull(response.getCookie(COOKIE));
            }
            assertEquals(List.of(201, 409), statuses.stream().sorted().toList());
            assertEquals(1, sessionCount(email));
        } finally {
            pool.shutdownNow();
            pool.awaitTermination(20, TimeUnit.SECONDS);
            db.sql("delete from app_user where email=?").param(email).update();
        }
    }

    private int sessionCount(String email) {
        return db.sql("select count(*) from refresh_session s join app_user u on u.id=s.user_id where u.email=?")
                .param(email).query(Integer.class).single();
    }
}
