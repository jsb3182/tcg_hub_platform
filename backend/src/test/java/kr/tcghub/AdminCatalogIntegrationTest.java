package kr.tcghub;

import java.util.*;
import java.util.concurrent.*;
import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.ObjectNode;
import jakarta.servlet.http.Cookie;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.*;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.test.context.transaction.TestTransaction;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;
import org.springframework.transaction.annotation.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest(properties={"tcg.public-origin=http://127.0.0.1:8080","server.address=127.0.0.1",
        "tcg.cf-audience=","tcg.cf-team-domain="})
@AutoConfigureMockMvc(print=MockMvcPrint.NONE)
@Transactional
@EnabledIfEnvironmentVariable(named="TCG_TEST_DB",matches="1")
class AdminCatalogIntegrationTest {
    private static final String BASE="/api/v1/admin/catalog";
    @Autowired MockMvc http;
    @Autowired JdbcClient db;
    @Autowired ObjectMapper json;
    @Autowired Tokens tokens;
    String email, jwt;
    Cookie factor;
    long userId;

    @BeforeEach void adminSession() {
        email=UUID.randomUUID()+"@fixture.invalid";
        userId=db.sql("insert into app_user(email,password_hash,role) values(?,'fixture','ROLE_ADMIN') returning id")
                .param(email).query(Long.class).single();
        db.sql("insert into local_admin_factor(user_id,secret_base32) values(?,?)").param(userId).param("A".repeat(32)).update();
        String token=UUID.randomUUID().toString().replace("-","")+"A".repeat(11);
        db.sql("insert into local_admin_session(token_hash,user_id,expires_at) values(?,?,now()+interval '1 hour')")
                .param(Accounts.hash(token)).param(userId).update();
        factor=new Cookie(LocalAdmin.COOKIE,token);
        jwt=tokens.issue(email,"ROLE_ADMIN");
    }

    @AfterEach void cleanupCommittedFixture() {
        if (TestTransaction.isActive()) return;
        db.sql("delete from card where id in (select target_id from operator_action where user_id=? and action='CREATE_CARD')")
                .param(userId).update();
        db.sql("delete from operator_action where user_id=?").param(userId).update();
        db.sql("delete from app_user where id=?").param(userId).update();
    }

    MockHttpServletRequestBuilder local(MockHttpServletRequestBuilder request) {
        return request.header("Host","127.0.0.1:8080").header("Origin",LocalAdmin.LOCAL_ORIGIN).header("X-TCG-Request","1")
                .contentType("application/json").with(r -> {
                    r.setLocalAddr("127.0.0.1"); r.setRemoteAddr("127.0.0.1"); r.setLocalPort(8080);
                    r.setServletPath(r.getRequestURI()); return r;
                });
    }
    MockHttpServletRequestBuilder admin(MockHttpServletRequestBuilder request) {
        return local(request).header("Authorization","Bearer "+jwt).cookie(factor);
    }
    JsonNode save(MockHttpServletRequestBuilder request,ObjectNode input,int expected) throws Exception {
        var result=http.perform(admin(request).content(json.writeValueAsBytes(input))).andExpect(status().is(expected)).andReturn();
        return expected<300 ? json.readTree(result.getResponse().getContentAsByteArray()) : null;
    }
    ObjectNode draft(String game,String name) { return json.createObjectNode().put("gameCode",game).put("name",name); }

    @Test void operatorCanPublishEditAndWithdrawWithinTheSelectedGame() throws Exception {
        var pack=draft("POKEMON","관리 테스트 팩").put("code","QA").put("releaseDate","2026-09-01");
        pack.putObject("metadata").put("language","ko");
        var createdPack=save(post(BASE+"/packs"),pack,201);
        long packId=createdPack.get("id").asLong();
        assertTrue(createdPack.get("editable").asBoolean());
        assertEquals("ko",createdPack.at("/metadata/language").asText());
        pack.put("version",1).put("releaseLabel","가을");
        assertEquals(2,save(put(BASE+"/packs/"+packId),pack,200).get("version").asInt());
        save(put(BASE+"/packs/"+packId),pack,409);
        http.perform(admin(get(BASE+"/packs").param("q","관리 테스트 팩").param("game","POKEMON")))
                .andExpect(jsonPath("$.items[0].id").value(packId));
        var card=draft("POKEMON","관리 테스트 카드").put("packId",packId).put("number","QA-1").put("rarity","R");
        card.putObject("specs").put("hp",120).putArray("types").add("Water");
        var created=save(post(BASE+"/cards"),card,201);
        long id=created.get("id").asLong();
        assertTrue(created.get("variantId").isIntegralNumber());
        assertEquals("PENDING",created.get("status").asText());
        http.perform(get("/api/v1/cards/"+id)).andExpect(status().isNotFound());
        http.perform(admin(get(BASE+"/cards").param("status","PENDING").param("q","QA-1").param("size","1")))
                .andExpect(jsonPath("$.items[0].specs.hp").value(120)).andExpect(jsonPath("$.items[0].id").value(id));
        card.put("version",1).put("status","PUBLISHED").put("rarity","SR");
        var updated=save(put(BASE+"/cards/"+id),card,200);
        assertEquals(2,updated.get("version").asLong());
        assertEquals(created.get("variantId"),updated.get("variantId"));
        http.perform(get("/api/v1/cards/"+id)).andExpect(status().isOk()).andExpect(jsonPath("$.variants[0].rarity").value("SR"));
        save(put(BASE+"/cards/"+id),card,409);
        card.put("version",2).put("status","PENDING");
        save(put(BASE+"/cards/"+id),card,200);
        http.perform(get("/api/v1/cards/"+id)).andExpect(status().isNotFound());
        assertEquals(5,db.sql("select count(*) from operator_action where user_id=?").param(userId).query(Integer.class).single());
    }

    @Test void sourceOwnedRecordsAndInvalidInputCannotBeWritten() throws Exception {
        long p=db.sql("insert into pack(game_code,name,legacy_key) values('WEISS','Source',?) returning id")
                .param("catalog:WEISS:"+UUID.randomUUID()).query(Long.class).single();
        long c=db.sql("insert into card(game_code,name,status,source_id) select 'WEISS','Source','PENDING',id from feed_source where provider='CATALOG' and source_key='WEISS' returning id")
                .query(Long.class).single();
        var pack=draft("WEISS","Edit").put("version",1);
        pack.putObject("metadata");
        save(put(BASE+"/packs/"+p),pack,409);
        var card=draft("WEISS","Edit").put("status","PUBLISHED").put("version",1);
        card.putObject("specs");
        save(put(BASE+"/cards/"+c),card,409);
        http.perform(admin(get(BASE+"/cards/"+c))).andExpect(jsonPath("$.editable").value(false))
                .andExpect(jsonPath("$.status").value("PENDING"));
        db.sql("update card set name='Source update',edit_version=edit_version+1 where id=?").param(c).update();
        var approval=json.createObjectNode().put("status","PUBLISHED").put("version",1);
        save(put(BASE+"/cards/"+c+"/status"),approval,409);
        var approved=save(put(BASE+"/cards/"+c+"/status"),approval.put("version",2),200);
        assertEquals("Source update",approved.get("name").asText());
        assertEquals("PUBLISHED",approved.get("status").asText());
        assertFalse(approved.get("editable").asBoolean());
        save(post(BASE+"/cards"),draft("POKEMON","Test").put("packId",p),400);
        save(post(BASE+"/cards"),draft("OTHER","Test"),400);
        save(post(BASE+"/packs"),draft("NIVEL","  "),400);
        save(post(BASE+"/cards"),draft("WEISS","Test").put("effect","X".repeat(8001)),400);
        var malformed=draft("RIFTBOUND","Test");
        malformed.putObject("specs").put("domains","Chaos");
        save(post(BASE+"/cards"),malformed,400);
        malformed.putObject("specs").put("other","X".repeat(16400));
        save(post(BASE+"/cards"),malformed,400);
        malformed.putArray("specs");
        save(post(BASE+"/cards"),malformed,400);
        var manual=save(post(BASE+"/cards"),draft("NIVEL","Test"),201);
        card=draft("NIVEL","Edit").put("status","PUBLISHED");
        card.putObject("specs");
        save(put(BASE+"/cards/"+manual.get("id")),card,400);
        card.put("version",1).put("gameCode","WEISS");
        save(put(BASE+"/cards/"+manual.get("id")),card,400);
    }

    @Test void accessRequiresAdminRoleAndTheSecondFactor() throws Exception {
        String url=BASE+"/cards";
        http.perform(local(get(url))).andExpect(status().isUnauthorized());
        http.perform(local(post(url)).header("Authorization","Bearer "+jwt).content("{}")).andExpect(status().isForbidden());
        http.perform(local(get(url)).header("Authorization","Bearer "+tokens.issue(email,"ROLE_USER")).cookie(factor))
                .andExpect(status().isForbidden());
    }

    @Test @Transactional(propagation=Propagation.NOT_SUPPORTED)
    void simultaneousSavesOfOneVersionCommitExactlyOneUpdate() throws Exception {
        long id=save(post(BASE+"/cards"),draft("YUGIOH","Concurrency"),201).get("id").asLong();
        var ready=new CountDownLatch(2);
        var pool=Executors.newFixedThreadPool(2);
        try {
            List<Future<Integer>> writes=new ArrayList<>();
            for (String name:List.of("First","Second")) {
                writes.add(pool.submit(() -> {
                    var card=draft("YUGIOH",name).put("version",1).put("status","PENDING");
                    card.putObject("specs");
                    ready.countDown();
                    assertTrue(ready.await(5,TimeUnit.SECONDS));
                    return http.perform(admin(put(BASE+"/cards/"+id)).content(json.writeValueAsBytes(card)))
                            .andReturn().getResponse().getStatus();
                }));
            }
            assertEquals(Set.of(200,409),Set.of(writes.get(0).get(10,TimeUnit.SECONDS),writes.get(1).get(10,TimeUnit.SECONDS)));
            http.perform(admin(get(BASE+"/cards/"+id))).andExpect(jsonPath("$.version").value(2));
        } finally { pool.shutdownNow(); }
    }
}
