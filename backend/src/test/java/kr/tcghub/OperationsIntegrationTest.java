package kr.tcghub;

import java.time.Instant;
import java.util.UUID;
import com.nimbusds.jose.JOSEException;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.gen.RSAKeyGenerator;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.*;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;
import org.springframework.transaction.annotation.Transactional;
import static org.junit.jupiter.api.Assertions.*;
import static org.hamcrest.Matchers.contains;
import static kr.tcghub.TestAccessProvider.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest(properties={"tcg.cf-team-domain=tcg-test-fixture.cloudflareaccess.com","tcg.cf-audience=test-ops"})
@AutoConfigureMockMvc
@Import(TestAccessProvider.class)
@Transactional
@EnabledIfEnvironmentVariable(named="TCG_TEST_DB",matches="1")
class OperationsIntegrationTest {
    @Autowired MockMvc http;
    @Autowired JdbcClient db;
    @Autowired Tokens tokens;
    @Value("${tcg.public-origin}") String origin;
    @Autowired RSAKey key;
    String access;
    String admin;
    long source;
    long item;

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

    @Test void hostRoutesRequireBothFactorsAndSchedulerStopsClaimingNewSources() throws Exception {
        String base="/api/admin/server";
        http.perform(get(base+"/status")).andExpect(status().isUnauthorized());
        http.perform(get(base+"/status").header("Authorization","Bearer "+admin)).andExpect(status().isForbidden());
        http.perform(get(base+"/status").header("Authorization","Bearer "+admin).header(ASSERTION,access))
                .andExpect(status().isOk()).andExpect(jsonPath("$.database").value("UP"));
        for (String action:java.util.List.of("scheduler/pause","crawler/stop","sync")) {
            String full=base+"/"+action;
            http.perform(post(full).servletPath(full).header("Origin",origin).header("X-TCG-Request","1")
                    .header(ASSERTION,access).header("Authorization","Bearer "+admin))
                    .andExpect(status().is2xxSuccessful());
        }
        org.junit.jupiter.api.Assertions.assertTrue(db.sql("select not scheduler_enabled and not crawler_enabled from collection_control")
                .query(Boolean.class).single());
    }

    @Test void hiddenReviewedPostStaysInModerationAndCanBeRepublishedAndPinned() throws Exception {
        http.perform(command("/review/"+item+"/decision").content("{\"status\":\"PUBLISHED\"}"))
                .andExpect(status().isNoContent());
        http.perform(command("/posts/"+item+"/visibility").content("{\"hidden\":true,\"pinned\":false}"))
                .andExpect(status().isNoContent());
        http.perform(get("/api/v1/news?game=NIVEL&size=100")).andExpect(jsonPath("$.items[?(@.id=="+item+")]").isEmpty());
        http.perform(command("/posts/"+item+"/visibility").content("{\"hidden\":false,\"pinned\":true}"))
                .andExpect(status().isNoContent());
        http.perform(get("/api/v1/news?game=NIVEL")).andExpect(jsonPath("$.items[0].id").value(item));
    }

    @Test void xSubscriptionsValidateHandlesAndStartUnderModeration() throws Exception {
        String path="/sources/x";
        long shop=db.sql("select min(id) from store").query(Long.class).single();
        String request="""
            {"username":"@ShopTest","gameCode":"ONEPIECE","storeId":%d}
            """.formatted(shop);
        String full="/api/v1/admin"+path;
        http.perform(post(full).servletPath(full).header("Origin",origin).header("X-TCG-Request","1")
                .contentType("application/json").content(request)).andExpect(status().isUnauthorized());
        http.perform(post(full).servletPath(full).header("Origin",origin).header("X-TCG-Request","1")
                .header("Authorization","Bearer "+admin).contentType("application/json").content(request))
                .andExpect(status().isForbidden());
        http.perform(command(path).content(request)).andExpect(status().isCreated()).andExpect(jsonPath("$.id").isNumber());
        assertTrue(db.sql("""
            select not auto_publish and game_code='ONEPIECE' and store_id=? and interval_seconds=3600
              from feed_source where provider='X' and source_key='ShopTest'
            """).param(shop).query(Boolean.class).single());
        http.perform(command(path).content(request.replace("@ShopTest","shoptest"))).andExpect(status().isConflict());
        http.perform(command(path).content(request.replace("@ShopTest","bad/handle"))).andExpect(status().isBadRequest());
        http.perform(command(path).content(request.replace("ONEPIECE","UNKNOWN"))).andExpect(status().isBadRequest());
        http.perform(command(path).content("{\"username\":\"OtherTest\",\"storeId\":9223372036854775807}"))
                .andExpect(status().isBadRequest());
        http.perform(command(path).content("{\"username\":\"OtherTest\"}")).andExpect(status().isCreated());
    }

    @Test void storeNoticeFollowsModerationVisibilityAndSourcePolicy() throws Exception {
        long shop=db.sql("select min(id) from store where listed").query(Long.class).single();
        db.sql("update feed_source set provider='X',game_code=null,store_id=? where id=?").param(shop).param(source).update();
        db.sql("""
            insert into calendar_event(store_id,feed_item_id,source_event_key,title,category,starts_at,status)
            values(?,?,'store-notice','검수 확인 대회','TOURNAMENT',now()+interval '1 day','PENDING')
            """).param(shop).param(item).update();
        String storeName=db.sql("select name from store where id=?").param(shop).query(String.class).single();
        var lookup=get("/api/v1/stores").param("q",storeName);
        String match="$.items[?(@.id=="+shop+")].events[*].title";
        http.perform(lookup).andExpect(jsonPath(match,org.hamcrest.Matchers.not(org.hamcrest.Matchers.hasItem("검수 확인 대회"))));
        http.perform(command("/review/"+item+"/decision").content("{\"status\":\"PUBLISHED\",\"gameCode\":\"NIVEL\"}"))
                .andExpect(status().isNoContent());
        assertEquals("NIVEL", db.sql("select game_code from calendar_event where feed_item_id=?").param(item).query(String.class).single());
        http.perform(lookup).andExpect(jsonPath(match,org.hamcrest.Matchers.hasItem("검수 확인 대회")));
        http.perform(command("/posts/"+item+"/visibility").content("{\"hidden\":true,\"pinned\":false}"))
                .andExpect(status().isNoContent());
        http.perform(lookup).andExpect(jsonPath(match,org.hamcrest.Matchers.not(org.hamcrest.Matchers.hasItem("검수 확인 대회"))));
        db.sql("update feed_item set hidden=false where id=?").param(item).update();
        db.sql("update feed_source set enabled=false, policy_note='이용 중지' where id=?").param(source).update();
        http.perform(lookup).andExpect(jsonPath(match,org.hamcrest.Matchers.not(org.hamcrest.Matchers.hasItem("검수 확인 대회"))));
    }

    @Test void approvedStorePublishesOnlyThisWeeksTournament() throws Exception {
        String name="test-"+UUID.randomUUID();
        String edit="""
            {"name":"%s","address":"서울","region":"서울","lat":37.56,"lon":126.98,
             "gameCodes":["ONEPIECE"],"official":true,"listed":true}
            """.formatted(name);
        http.perform(command("/stores").content(edit)).andExpect(status().isCreated());
        long store=db.sql("select id from store where name=?").param(name).query(Long.class).single();
        String path="/stores/"+store+"/events";
        for (int days : new int[]{1,14}) {
            String start=java.time.OffsetDateTime.now(java.time.ZoneOffset.UTC).plusDays(days).withNano(0).toString();
            http.perform(command(path).content("""
                {"title":"대회","gameCode":"ONEPIECE","startsAt":"%s"}
                """.formatted(start))).andExpect(status().isCreated());
        }
        http.perform(get("/api/v1/stores").param("q",name).param("game","ONEPIECE"))
                .andExpect(jsonPath("$.items[0].official").value(true))
                .andExpect(jsonPath("$.items[0].events.length()").value(1));
        db.sql("update app_user set role='ROLE_USER' where email=(select email from app_user where id=(select user_id from operator_action where action='CREATE_STORE' and target_id=?))")
                .param(store).update();
        http.perform(command(path).content("{}")).andExpect(status().isForbidden());
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

    @Test void restrictedSourceIsHiddenAndCannotBeResumedFromTheDashboard() throws Exception {
        db.sql("update feed_item set status='PUBLISHED' where id=?").param(item).update();
        long visible = newsCount();
        db.sql("update feed_source set enabled=false,policy_note='테스트 이용 조건' where id=?").param(source).update();
        assertEquals(visible-1,newsCount());
        assertEquals("PUBLISHED",db.sql("select status from feed_item where id=?").param(item).query(String.class).single());
        http.perform(get("/api/v1/admin/operations").header(ASSERTION,access).header("Authorization","Bearer "+admin))
                .andExpect(jsonPath("$.sources[?(@.id == " + source + ")].policyNote").value(contains("테스트 이용 조건")));
        http.perform(command("/sources/"+source+"/enabled").content("{\"enabled\":true}")).andExpect(status().isConflict());
        http.perform(command("/sources/"+source+"/run")).andExpect(status().isConflict());
    }

    @Test void dashboardPreservesProviderCooldownForManualRequests() throws Exception {
        db.sql("""
            insert into feed_provider_cooldown(provider,retry_after_at) values('X','2099-02-02T00:00:00Z')
            on conflict(provider) do update set retry_after_at=excluded.retry_after_at
            """).update();
        long xSource = db.sql("""
            insert into feed_source(provider,source_key,retry_after_at) values('X',?,'2099-02-01T00:00:00Z') returning id
            """).param(UUID.randomUUID().toString()).query(Long.class).single();
        db.sql("update feed_source set next_fetch_at='2099-02-01T00:00:00Z' where id=?").param(source).update();
        http.perform(command("/sources/"+xSource+"/run")).andExpect(status().isNoContent());

        String x = "$.sources[?(@.id == " + xSource + ")]";
        String other = "$.sources[?(@.id == " + source + ")]";
        var dashboard = get("/api/v1/admin/operations").header(ASSERTION,access).header("Authorization","Bearer "+admin);
        http.perform(dashboard).andExpect(status().isOk())
                .andExpect(jsonPath(x+".state").value(contains("QUEUED")))
                .andExpect(jsonPath(x+".nextFetchAt").value(contains("2099-02-02T00:00:00Z")))
                .andExpect(jsonPath(other+".nextFetchAt").value(contains("2099-02-01T00:00:00Z")));

        db.sql("update feed_source set retry_after_at='2099-02-03T00:00:00Z' where id=?").param(xSource).update();
        http.perform(dashboard).andExpect(status().isOk())
                .andExpect(jsonPath(x+".nextFetchAt").value(contains("2099-02-03T00:00:00Z")));
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

    @Test void translationsFollowRequestedLanguageWithoutPublishingReviewItemsOrReplacingOriginalText() throws Exception {
        db.sql("""
            update feed_item set source_published_at='2199-01-01T00:00:00Z',
                payload='{"kind":"NEWS","title":"Source title","summary":"Source summary"}' where id=?
            """).param(item).update();
        db.sql("update feed_item set original_language='en' where id=?").param(item).update();
        db.sql("insert into feed_item_translation(item_id,lang,title,summary) values(?,'ko','한국어 제목','한국어 요약')")
                .param(item).update();
        var news = get("/api/v1/news").param("game","NIVEL");
        http.perform(news).andExpect(status().isOk()).andExpect(jsonPath("$.items[?(@.id == "+item+")]").isEmpty());
        http.perform(get("/api/v1/admin/review").header("Authorization","Bearer "+admin).header(ASSERTION,access)
                .param("lang","ko")).andExpect(status().isOk()).andExpect(jsonPath("$.items[0].id").value(item))
                .andExpect(jsonPath("$.items[0].translationStatus").value("TRANSLATED"));
        db.sql("update feed_item set status='PUBLISHED' where id=?").param(item).update();
        http.perform(news).andExpect(status().isOk()).andExpect(jsonPath("$.items[0].id").value(item))
                .andExpect(jsonPath("$.items[0].title").value("한국어 제목"))
                .andExpect(jsonPath("$.items[0].summary").value("한국어 요약"))
                .andExpect(jsonPath("$.items[0].originalTitle").value("Source title"))
                .andExpect(jsonPath("$.items[0].originalSummary").value("Source summary"))
                .andExpect(jsonPath("$.items[0].originalLanguage").value("en"))
                .andExpect(jsonPath("$.items[0].contentLanguage").value("ko"))
                .andExpect(jsonPath("$.items[0].summaryLanguage").value("ko"))
                .andExpect(jsonPath("$.items[0].translationStatus").value("TRANSLATED"))
                .andExpect(jsonPath("$.items[0].sourceUrl").value("https://example.invalid/news"));
        http.perform(get("/api/v1/news").param("game","NIVEL").param("lang","en"))
                .andExpect(jsonPath("$.items[0].translationStatus").value("ORIGINAL"))
                .andExpect(jsonPath("$.items[0].title").value("Source title"))
                .andExpect(jsonPath("$.items[0].contentLanguage").value("en"));
        http.perform(get("/api/v1/news").param("game","NIVEL").param("lang","ja"))
                .andExpect(jsonPath("$.items[0].translationStatus").value("PENDING"))
                .andExpect(jsonPath("$.items[0].summary").value("Source summary"))
                .andExpect(jsonPath("$.items[0].contentLanguage").value("en"));
        db.sql("update feed_item_translation set summary=null where item_id=? and lang='ko'").param(item).update();
        http.perform(news).andExpect(jsonPath("$.items[0].title").value("한국어 제목"))
                .andExpect(jsonPath("$.items[0].summary").value("Source summary"))
                .andExpect(jsonPath("$.items[0].contentLanguage").value("ko"))
                .andExpect(jsonPath("$.items[0].summaryLanguage").value("en"));
        db.sql("update feed_item set original_language=null where id=?").param(item).update();
        http.perform(get("/api/v1/news").param("game","NIVEL").param("lang","ja"))
                .andExpect(jsonPath("$.items[0].translationStatus").value("PENDING"))
                .andExpect(jsonPath("$.items[0].contentLanguage").value(org.hamcrest.Matchers.nullValue()));
        for (String invalid : new String[]{"fr","en-US","","ko' OR 1=1 --"}) {
            http.perform(get("/api/v1/news").param("lang",invalid)).andExpect(status().isBadRequest());
        }
    }

    private long newsCount() throws Exception {
        var response=http.perform(get("/api/v1/news").param("game","NIVEL"))
                .andExpect(status().isOk()).andReturn().getResponse().getContentAsString();
        return new com.fasterxml.jackson.databind.ObjectMapper().readTree(response).get("total").asLong();
    }
}
