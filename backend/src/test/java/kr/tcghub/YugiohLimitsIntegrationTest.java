package kr.tcghub;

import java.util.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.*;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;
import org.springframework.transaction.annotation.Transactional;
import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
@Transactional
@EnabledIfEnvironmentVariable(named="TCG_TEST_DB",matches="1")
class YugiohLimitsIntegrationTest {
    @Autowired YugiohLimits limits;
    @Autowired JdbcClient db;
    @Autowired MockMvc api;
    @Autowired Tokens tokens;
    @Autowired ObjectMapper json;
    @Value("${tcg.public-origin}") String origin;
    String token;
    long source;

    @BeforeEach void start() {
        var email = UUID.randomUUID()+"@example.invalid";
        db.sql("insert into app_user(email,password_hash) values(?,'unused')").param(email).update();
        source = db.sql("select id from feed_source where provider='CATALOG' and source_key='YUGIOH'").query(Long.class).single();
        token = tokens.issue(email,"ROLE_USER");
        db.sql("update yugioh_limit_list set verified_on=current_date,evidence_status='VERIFIED'").update();
    }
    private long card(int cid, String name, String effect) {
        return db.sql("""
                insert into card(game_code,source_id,legacy_key,name,original_name,status,effect,specs)
                values('YUGIOH',?,?,?,?, 'PUBLISHED',?,jsonb_build_object('konami_id',cast(? as int),'formats','["OCG","TCG"]'::jsonb,
                  'tcg_date','2005-01-01','ocg_date','2005-01-01','type','Effect Monster')) returning id
                """).param(source).param("catalog:YUGIOH:fixture-"+UUID.randomUUID()).param(name).param(name)
                .param(effect).param(cid).query(Long.class).single();
    }
    private static DeckRules.Line line(long id,String section,int quantity) { return new DeckRules.Line(id,section,quantity); }
    private MockHttpServletRequestBuilder write(MockHttpServletRequestBuilder req,Object body) throws Exception {
        return req.header("Authorization","Bearer "+token).header("Origin",origin).header("X-TCG-Request","1")
                .contentType(MediaType.APPLICATION_JSON).content(json.writeValueAsBytes(body));
    }
    @Test void realDatedLimitsCombineAcrossSectionsPrintingsAndArtworkAndPreserveRegionalDifferences() {
        // Synthetic card rows carry the real official CIDs. Do not require the full live catalog in a fresh test database.
        long banned = card(4844,"Pot of Greed","");
        long first = card(9279,"Droll & Lock Bird","");
        long second = card(9279,"Droll & Lock Bird","");
        long maxx = card(9455,"Maxx \"C\"","");
        var rows = List.of(line(banned,"MAIN",1),line(first,"MAIN",1),new DeckRules.Line(second,"SIDE",1,null,2),
                           line(maxx,"SIDE",1));
        var ocg=limits.check("OCG",rows);
        var tcg=limits.check("TCG",rows);
        assertEquals("2026-10-01",ocg.effectiveOn().toString());
        assertEquals("2026-10-19",tcg.effectiveOn().toString());
        assertEquals("CHECKED",ocg.status());
        assertEquals("CHECKED",tcg.status());
        assertTrue(tcg.violations().stream().anyMatch(v->v.cardId()==banned && v.limit()==0 && v.copies()==1));
        assertTrue(tcg.violations().stream().anyMatch(v->v.cardId()==first && v.limit()==1 && v.copies()==2));
        assertTrue(tcg.violations().stream().anyMatch(v->v.cardId()==maxx && v.limit()==0));
        assertFalse(ocg.violations().stream().anyMatch(v->v.cardId()==maxx));
        long same = card(1000001,"Harpie Lady","");
        long alternate = card(1000002,"Cyber Harpie Lady","(This card's name is always treated as \"Harpie Lady\".)");
        var alias=limits.check("TCG",List.of(line(same,"MAIN",2),line(alternate,"SIDE",2)));
        assertEquals(4,alias.violations().get(0).copies());
        assertEquals(3,alias.violations().get(0).limit());
        long newer=card(1000003,"New printing","");
        db.sql("update card set specs=jsonb_set(specs,'{tcg_date}',to_jsonb(to_char(current_date,'YYYY-MM-DD'))) where id=?")
                .param(newer).update();
        db.sql("update yugioh_limit_list set verified_on=current_date-1 where region='TCG'").update();
        assertEquals(List.of(newer),limits.check("TCG",List.of(line(newer,"MAIN",1))).unknownCardIds());
    }
    @Test void unresolvedRegionalIdentityDoesNotApproveCompleteAndDraftRetainsRegionAcrossHistoryAndCodes() throws Exception {
        long manual = db.sql("insert into card(game_code,name,status,specs) values('YUGIOH','manual','PUBLISHED','{\"konami_id\":4844}') returning id")
                .query(Long.class).single();
        var lines=List.of(line(manual,"MAIN",1));
        var check=Map.of("region","TCG","entries",lines);
        api.perform(write(post("/api/v1/me/decks/yugioh-limits"),check))
                .andExpect(status().isOk()).andExpect(jsonPath("$.status").value("PARTIAL"))
                .andExpect(jsonPath("$.unknownCardIds[0]").value(manual));
        var save=new DeckApi.Save("테스트","YUGIOH","DRAFT",0,true,lines,null,null,"TCG");
        var created=api.perform(write(post("/api/v1/me/decks"),save)).andExpect(status().isCreated())
                .andExpect(jsonPath("$.region").value("TCG")).andExpect(jsonPath("$.regionalLimits.status").value("PARTIAL"))
                .andExpect(jsonPath("$.rule.regions[0]").value("OCG")).andReturn();
        long id=json.readTree(created.getResponse().getContentAsByteArray()).get("id").asLong();
        var oldClient=new DeckApi.Save("수정","YUGIOH","DRAFT",1,true,lines);
        api.perform(write(put("/api/v1/me/decks/"+id),oldClient)).andExpect(status().isOk()).andExpect(jsonPath("$.region").value("TCG"));
        var completed=new DeckApi.Save("수정","YUGIOH","COMPLETE",2,true,lines);
        api.perform(write(put("/api/v1/me/decks/"+id),completed)).andExpect(status().isUnprocessableEntity());
        api.perform(get("/api/v1/me/decks/"+id+"/history/1").header("Authorization","Bearer "+token))
                .andExpect(status().isOk()).andExpect(jsonPath("$.region").value("TCG"));
        var code=api.perform(get("/api/v1/me/decks/"+id+"/code").header("Authorization","Bearer "+token))
                .andExpect(status().isOk()).andReturn();
        api.perform(write(post("/api/v1/me/decks/import"),json.readTree(code.getResponse().getContentAsByteArray())))
                .andExpect(status().isCreated()).andExpect(jsonPath("$.region").value("TCG"));
        var cleared=new DeckApi.Save("기본","YUGIOH","DRAFT",2,true,lines,null,null,"");
        api.perform(write(put("/api/v1/me/decks/"+id),cleared)).andExpect(status().isOk())
                .andExpect(jsonPath("$.region").isEmpty()).andExpect(jsonPath("$.regionalLimits").isEmpty());
        db.sql("update yugioh_limit_list set verified_on=current_date-8 where region='TCG'").update();
        assertEquals("UNAVAILABLE",limits.check("TCG",lines).status());
    }
}
