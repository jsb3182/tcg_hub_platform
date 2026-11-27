package kr.tcghub;

import java.util.List;
import java.util.Map;
import java.util.UUID;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.Cookie;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.*;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;
import org.springframework.transaction.annotation.Transactional;
import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties={"tcg.public-origin=http://127.0.0.1:8080","server.address=127.0.0.1",
        "tcg.cf-audience=","tcg.cf-team-domain="})
@AutoConfigureMockMvc(print=MockMvcPrint.NONE)
@EnabledIfEnvironmentVariable(named="TCG_TEST_DB",matches="1")
@Transactional
class CommunityIntegrationTest {
    static final String POSTS = "/api/v1/community/posts";
    static final String REPORTS = "/api/v1/community/reports";
    static final String ADMIN = "/api/v1/admin/community/reports";
    @Autowired MockMvc api;
    @Autowired JdbcClient db;
    @Autowired Tokens tokens;
    @Autowired ObjectMapper json;
    String owner, other, admin;
    String prefix;
    Cookie factor;

    @BeforeEach void members() {
        prefix = UUID.randomUUID().toString();
        owner = member("owner","ROLE_USER");
        other = member("reader","ROLE_USER");
        admin = member("moderator","ROLE_ADMIN");
        long id = db.sql("select id from app_user where email=?").param(email("moderator")).query(Long.class).single();
        db.sql("insert into local_admin_factor(user_id,secret_base32) values(?,?)").param(id).param("A".repeat(32)).update();
        String secret = UUID.randomUUID().toString().replace("-","")+"A".repeat(11);
        db.sql("insert into local_admin_session(user_id,token_hash,expires_at) values(?,?,now()+interval '1 hour')")
                .param(id).param(Accounts.hash(secret)).update();
        factor = new Cookie(LocalAdmin.COOKIE,secret);
    }
    private String email(String user) { return user+prefix+"@qa.invalid"; }
    private String member(String label,String role) {
        String email=email(label);
        db.sql("insert into app_user(email,password_hash,role) values(?,'fixture',?)").param(email).param(role).update();
        return tokens.issue(email,role);
    }
    private JsonNode call(MockHttpServletRequestBuilder req,String bearer,Object payload,int expected) throws Exception {
        req.header("Host","127.0.0.1:8080").header("Origin",LocalAdmin.LOCAL_ORIGIN).header("X-TCG-Request","1")
                .with(r->{r.setLocalAddr("127.0.0.1");r.setRemoteAddr("127.0.0.1");r.setLocalPort(8080);
                    r.setServletPath(r.getRequestURI());return r;});
        if (bearer!=null) req.header("Authorization","Bearer "+bearer);
        if (payload!=null) req.contentType("application/json").content(json.writeValueAsBytes(payload));
        var body=api.perform(req).andExpect(status().is(expected)).andReturn().getResponse().getContentAsByteArray();
        return expected>=300||body.length==0 ? null : json.readTree(body);
    }
    private long create(String board) throws Exception {
        return call(post(POSTS),owner,Map.of("board",board,"title",prefix,"body","두 줄\n본문"),201).get("id").asLong();
    }
    private long card(String visibility) {
        return db.sql("insert into card(game_code,name,number,status) values('POKEMON','한국판','T-001',?) returning id")
                .param(visibility).query(Long.class).single();
    }

    @Test void publicBoardsTagsAndTradeStatusPreserveOwnershipAndPrivateAccountData() throws Exception {
        long card=card("PUBLISHED");
        var input=Map.of("board","TRADE","title",prefix,"body","판매 <3","tradeType","SELL","cardIds",List.of(card));
        call(post(POSTS),null,input,401);
        long id=call(post(POSTS),owner,input,201).get("id").asLong();
        create("FREE"); create("SUGGESTION");
        var page=call(get(POSTS).param("board","TRADE").param("tradeType","SELL").param("q",prefix),null,null,200);
        assertEquals(1,page.get("total").asInt());
        assertFalse(page.at("/items/0/mine").asBoolean());
        var detail=call(get(POSTS+"/"+id),owner,null,200);
        assertTrue(detail.get("mine").asBoolean());
        assertEquals(card,detail.at("/cards/0/id").asLong());
        assertEquals("OPEN",detail.get("tradeStatus").asText());
        assertEquals("판매 <3",detail.get("body").asText());
        assertFalse(detail.toString().contains("@qa.invalid"));
        var route=POSTS+"/"+id+"/trade-status";
        call(patch(route),other,Map.of("tradeStatus","CLOSED"),403);
        var change=Map.of("tradeStatus","RESERVED","expectedTradeStatus","OPEN");
        call(patch(route),owner,change,200);
        call(patch(route),owner,change,200);
        call(patch(route),owner,Map.of("tradeStatus","CLOSED","expectedTradeStatus","OPEN"),409);
        call(patch(route),owner,Map.of("tradeStatus","CLOSED","expectedTradeStatus","RESERVED"),200);
        var closed=call(get(POSTS).param("tradeStatus","CLOSED").param("q",prefix),null,null,200);
        assertEquals(id,closed.at("/items/0/id").asLong());
        db.sql("update card set status='PENDING' where id=?").param(card).update();
        assertTrue(call(get(POSTS+"/"+id),null,null,200).get("cards").isEmpty());
    }

    @Test void badFieldsCardsAndCrossPostRepliesAreRejectedBeforeDataIsWritten() throws Exception {
        long draft=card("PENDING");
        call(post(POSTS),owner,Map.of("board","FREE","title",prefix,"body","본문","cardIds",List.of(draft)),400);
        call(post(POSTS),owner,Map.of("board","TRADE","title",prefix,"body","본문"),400);
        call(post(POSTS),owner,Map.of("board","FREE","title"," ","body","본문"),400);
        call(post(POSTS),owner,Map.of("board","FREE","title",prefix,"body","본문","tradeType","SELL"),400);
        assertEquals(0,call(get(POSTS).param("q",prefix),null,null,200).get("total").asInt());
        long first=create("FREE"),second=create("SUGGESTION");
        String path=POSTS+"/"+first+"/comments";
        long comment=call(post(path),other,Map.of("body","댓글"),201).get("id").asLong();
        long reply=call(post(path),owner,Map.of("body","대댓글","parentId",comment),201).get("id").asLong();
        call(post(path),owner,Map.of("body","또 다른 하위 답글","parentId",reply),400);
        call(post(POSTS+"/"+second+"/comments"),owner,Map.of("body","다른 게시글","parentId",comment),404);
        var result=call(get(path).param("page","1").param("size","1"),owner,null,200);
        assertEquals(2,result.get("total").asInt());
        assertTrue(result.at("/items/0/mine").asBoolean());
        assertEquals(comment,result.at("/items/0/parentId").asLong());
        call(post(REPORTS),owner,Map.of("postId",first,"commentId",comment,"reason","중복 대상"),400);
        db.sql("update app_user set enabled=false where email=?").param(email("reader")).update();
        call(post(path),other,Map.of("body","권한이 취소된 계정"),403);
    }

    @Test void onlySecondFactorAdminCanResolveReportsAndHideEntireCommentSubtree() throws Exception {
        long id=create("FREE");
        String path=POSTS+"/"+id+"/comments";
        long parent=call(post(path),other,Map.of("body","원댓글"),201).get("id").asLong();
        call(post(path),owner,Map.of("body","답글","parentId",parent),201);
        call(post(path),owner,Map.of("body","남는 댓글"),201);
        var input=Map.of("commentId",parent,"reason","확인 요청");
        long report=call(post(REPORTS),owner,input,201).get("id").asLong();
        call(post(REPORTS),owner,input,409);
        call(get(ADMIN),other,null,403);
        call(get(ADMIN),admin,null,403);
        var pending=call(get(ADMIN).cookie(factor),admin,null,200);
        var first=pending.at("/items/0");
        assertEquals(report,first.get("id").asLong());
        assertEquals(id,first.get("postId").asLong());
        assertEquals("원댓글",first.get("excerpt").asText());
        call(patch(ADMIN+"/"+report).cookie(factor),admin,Map.of("status","RESOLVED"),200);
        call(patch(ADMIN+"/"+report).cookie(factor),admin,Map.of("status","RESOLVED"),200);
        call(patch(ADMIN+"/"+report).cookie(factor),admin,Map.of("status","DISMISSED"),409);
        assertEquals(1,call(get(path),null,null,200).get("total").asInt());
        assertEquals(1,call(get(POSTS+"/"+id),null,null,200).get("commentCount").asInt());
        call(post(path),owner,Map.of("body","숨긴 댓글 답글","parentId",parent),404);
        call(post(REPORTS),other,input,404);
        long dismissed=call(post(REPORTS),owner,Map.of("postId",id,"reason","기각"),201).get("id").asLong();
        call(patch(ADMIN+"/"+dismissed).cookie(factor),admin,Map.of("status","DISMISSED"),200);
        call(get(POSTS+"/"+id),null,null,200);
        long hidden=call(post(REPORTS),other,Map.of("postId",id,"reason","비공개"),201).get("id").asLong();
        call(patch(ADMIN+"/"+hidden).cookie(factor),admin,Map.of("status","RESOLVED"),200);
        call(get(POSTS+"/"+id),null,null,404);
        call(get(path),null,null,404);
        assertEquals(0,call(get(POSTS).param("q",prefix),null,null,200).get("total").asInt());
    }
}
