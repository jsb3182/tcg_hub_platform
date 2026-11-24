package kr.tcghub;

import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.*;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;
import org.springframework.transaction.annotation.Transactional;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
@Transactional
@EnabledIfEnvironmentVariable(named="TCG_TEST_DB",matches="1")
class OperationsIntegrationTest {
    @Autowired MockMvc http;
    @Autowired JdbcClient db;
    @Autowired Tokens tokens;
    @Value("${tcg.public-origin}") String origin;
    @MockitoBean AccessGate gateway;
    String admin;
    long source;
    long item;

    @BeforeEach void setup() {
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
                .header("Origin",origin).header("X-TCG-Request","1").contentType("application/json");
    }

    @Test void gatewayAndRoleRequiredThenControlsReachDatabase() throws Exception {
        var snapshot = get("/api/v1/admin/operations").header("Authorization","Bearer "+admin);
        http.perform(snapshot).andExpect(status().isForbidden());
        when(gateway.admits(any())).thenReturn(true);
        http.perform(get("/api/v1/admin/operations")
                .header("Authorization","Bearer "+tokens.issue("reader@example.invalid","ROLE_USER")))
                .andExpect(status().isForbidden());
        http.perform(snapshot).andExpect(status().isOk()).andExpect(jsonPath("$.sources").isArray())
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
        when(gateway.admits(any())).thenReturn(true);
        db.sql("update feed_source set game_code=null where id=?").param(source).update();
        long before = newsCount();
        http.perform(get("/api/v1/admin/review").header("Authorization","Bearer "+admin)).andExpect(status().isOk());
        http.perform(command("/review/"+item+"/decision").content("{\"status\":\"PUBLISHED\",\"gameCode\":\"NIVEL\"}"))
                .andExpect(status().isNoContent());
        assertEquals(before+1,newsCount());
        http.perform(command("/review/"+item+"/decision").content("{\"status\":\"REJECTED\"}")).andExpect(status().isConflict());
        assertEquals(1,db.sql("select count(*) from operator_action where action='REVIEW_PUBLISHED' and target_id=?")
                .param(item).query(Integer.class).single());
    }

    private long newsCount() throws Exception {
        var response=http.perform(get("/api/v1/news").param("game","NIVEL"))
                .andExpect(status().isOk()).andReturn().getResponse().getContentAsString();
        return new com.fasterxml.jackson.databind.ObjectMapper().readTree(response).get("total").asLong();
    }
}
