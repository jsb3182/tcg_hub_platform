package kr.tcghub;

import java.util.*;
import com.fasterxml.jackson.databind.*;
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
@EnabledIfEnvironmentVariable(named="TCG_TEST_DB",matches="1")
@Transactional
class LibraryIntegrationTest {
    @Autowired MockMvc api;
    @Autowired JdbcClient db;
    @Autowired ObjectMapper json;
    @Autowired Tokens tokens;
    @Value("${tcg.public-origin}") String origin;
    String alice,bob;
    long first,second;
    @BeforeEach void fixtures() {
        alice=member();bob=member();
        first=card("YUGIOH","공개 카드","PUBLISHED");
        second=card("YUGIOH","공개 카드","PUBLISHED");
    }
    String member(){
        String email=UUID.randomUUID()+"@example.invalid";
        db.sql("insert into app_user(email,password_hash) values(?,'unused')").param(email).update();
        return tokens.issue(email,"ROLE_USER");
    }
    long card(String game,String name,String status){
        return db.sql("insert into card(game_code,name,status) values(?,?,?) returning id")
                .param(game).param(name).param(status).query(Long.class).single();
    }
    MockHttpServletRequestBuilder as(MockHttpServletRequestBuilder request,String token) {
        return request.header("Authorization","Bearer "+token).header("Origin",origin).header("X-TCG-Request","1");
    }
    MockHttpServletRequestBuilder write(MockHttpServletRequestBuilder req,String token,Object data) throws Exception {
        return as(req,token).contentType(MediaType.APPLICATION_JSON).content(json.writeValueAsBytes(data));
    }
    String binder(long id){return "/api/v1/me/binder/"+id;}

    @Test void threeEditionFieldsAndPortableOnePieceDeckUsePublishedPrintings() throws Exception {
        String game="ONEPIECE", path="/api/v1/me/decks";
        long leader=card(game,"시험 리더","PUBLISHED"), unit=card(game,"시험 캐릭터","PUBLISHED"), don=card(game,"두웅!!","PUBLISHED");
        db.sql("""
            update card set number='ST99-001',legacy_key='catalog:ONEPIECE:fixture',
            effect='공식 한국어 효과',specs='{"type":"leader","colors":["red"],"language":"ko",
            "names":{"ja":"試験リーダー","en":"Test Leader"},"texts":{"ja":"日本語の効果"},
            "images":{"ko":"https://www.onepiece-cardgame.kr/fileDownload?downname=test"}}' where id=?
            """).param(leader).update();
        db.sql("update card set specs='{\"type\":\"character\",\"colors\":[\"red\"]}',effect='You may have any number of this card in your deck.' where id=?")
                .param(unit).update();
        db.sql("update card set specs='{\"type\":\"don\"}' where id=?").param(don).update();
        for(String endpoint:List.of("/api/v1/cards/"+leader,"/api/v1/cards","/api/v1/play/cards")){
            var result=api.perform(get(endpoint).param("game",game).param("q","Test Leader").param("lang","ja"))
                    .andExpect(status().isOk()).andReturn().getResponse();
            var value=json.readTree(result.getContentAsByteArray());
            var row=value.isArray()?value.get(0):value.has("items")?value.get("items").get(0):value;
            assertEquals("試験リーダー",row.get("name").asText());
            assertEquals("ja",row.get("effectLanguage").asText());
            assertEquals("ko",row.get("imageLanguage").asText());
        }
        var legal=new DeckApi.Save("검증 덱",game,"COMPLETE",0,false,List.of(new DeckRules.Line(leader,"LEADER",1),
                new DeckRules.Line(unit,"MAIN",50),new DeckRules.Line(don,"DON",10)));
        var created=api.perform(write(post(path),alice,legal)).andExpect(status().isCreated()).andReturn().getResponse();
        long id=json.readTree(created.getContentAsByteArray()).get("id").asLong();
        var exported=api.perform(as(get(path+"/"+id+"/code"),alice)).andExpect(status().isOk()).andReturn().getResponse();
        var code=json.readTree(exported.getContentAsByteArray());
        api.perform(write(post(path+"/import"),bob,code)).andExpect(status().isCreated())
                .andExpect(jsonPath("$.state").value("DRAFT")).andExpect(jsonPath("$.entries.length()").value(3))
                .andExpect(jsonPath("$.shareToken").doesNotExist());
        var restrictions=new DeckRules(db);
        db.sql("update card set number='OP06-047' where id=?").param(unit).update();
        assertThrows(DeckRules.Invalid.class,()->restrictions.validate(restrictions.current(game),legal.entries(),true));
        db.sql("update card set number='OP05-041' where id=?").param(unit).update();
        restrictions.validate(restrictions.current(game),legal.entries(),true);
        db.sql("update card set specs=jsonb_set(specs,'{colors}','[\"green\"]') where id=?").param(unit).update();
        api.perform(write(post(path),alice,legal)).andExpect(status().isUnprocessableEntity());
        db.sql("update card set status='PENDING' where id=?").param(unit).update();
        api.perform(write(post(path+"/import"),bob,code)).andExpect(status().isUnprocessableEntity());
    }

    @Test void radianceRulesRejectBansAndMismatchedChampions() throws Exception {
        String game="RIFTBOUND";
        long banned=card(game,"Zhonya’s Hourglass","PUBLISHED"), legend=card(game,"Fixture Legend","PUBLISHED"), champion=card(game,"Fixture Champion","PUBLISHED");
        db.sql("update card set specs='{\"type\":\"legend\",\"domains\":[\"fury\"],\"tags\":[\"A\"]}' where id=?").param(legend).update();
        db.sql("update card set specs='{\"type\":\"unit\",\"supertype\":\"champion\",\"domains\":[\"fury\"],\"tags\":[\"B\"]}' where id=?").param(champion).update();
        var rules=new DeckRules(db);
        var current=rules.current(game);
        assertEquals(3,current.version());
        assertEquals(10,current.sections().stream().filter(s->s.section().equals("SIDE")).findFirst().orElseThrow().maxCards());
        assertThrows(DeckRules.Invalid.class,()->rules.validate(current,List.of(new DeckRules.Line(banned,"MAIN",1)),false));
        var pair=List.of(new DeckRules.Line(legend,"LEGEND",1),new DeckRules.Line(champion,"CHAMPION",1));
        assertThrows(DeckRules.Invalid.class,()->rules.validate(current,pair,false));
        db.sql("update card set specs=jsonb_set(specs,'{tags}','[\"A\"]') where id=?").param(champion).update();
        rules.validate(current,pair,false);
        assertEquals(2,rules.rule(game,"CONSTRUCTED",2).version());
    }

    @Test void separatePhysicalPrintingsHaveIndependentQuantitiesAndOneUniqueCard() throws Exception {
        api.perform(write(put(binder(first)),alice,new BinderApi.Quantity(2,0))).andExpect(status().isOk());
        var japanese=put(binder(first)).param("edition","ja").param("condition","NM").param("tradable","true");
        api.perform(write(japanese,alice,new BinderApi.Quantity(3,0))).andExpect(status().isOk());
        api.perform(as(get("/api/v1/me/binder").param("edition","ja").param("tradable","true"),alice))
                .andExpect(jsonPath("$.copies").value(3)).andExpect(jsonPath("$.items[0].condition").value("NM"));
        api.perform(as(get("/api/v1/me/binder/stats"),alice))
                .andExpect(jsonPath("$[?(@.gameCode=='YUGIOH')].uniqueCards").value(org.hamcrest.Matchers.contains(1)))
                .andExpect(jsonPath("$[?(@.gameCode=='YUGIOH')].copies").value(org.hamcrest.Matchers.contains(5)));
    }
    @Test void binderIsOwnerScopedAndConcurrentEditsAreDetected() throws Exception {
        api.perform(get("/api/v1/me/binder")).andExpect(status().isUnauthorized());
        api.perform(write(put(binder(first)),alice,new BinderApi.Quantity(3,0))).andExpect(status().isOk());
        api.perform(write(put(binder(first)),alice,new BinderApi.Quantity(4,0))).andExpect(status().isConflict());
        api.perform(as(get("/api/v1/me/binder"),alice)).andExpect(jsonPath("$.copies").value(3));
        api.perform(as(get("/api/v1/me/binder"),bob)).andExpect(jsonPath("$.total").value(0));
        api.perform(write(put(binder(first)),bob,new BinderApi.Quantity(0,0))).andExpect(status().isOk());
        api.perform(as(get(binder(first)),alice)).andExpect(jsonPath("$.quantity").value(3));
        api.perform(write(put(binder(first)),alice,new BinderApi.Quantity(0,3))).andExpect(status().isOk());
        api.perform(as(get("/api/v1/me/binder"),alice)).andExpect(jsonPath("$.total").value(0));
        api.perform(write(put(binder(card("YUGIOH","검수 대기","PENDING"))),alice,new BinderApi.Quantity(1,0))).andExpect(status().isNotFound());
    }
    DeckApi.Save save(int revision,boolean shared,String state,DeckRules.Line... lines){
        return new DeckApi.Save("연습 덱","YUGIOH",state,revision,shared,List.of(lines));
    }
    @Test void saveHistorySharingRevocationAndOwnerChecks() throws Exception {
        String path="/api/v1/me/decks";
        var original=save(0,true,"DRAFT",new DeckRules.Line(first,"MAIN",1));
        var result=api.perform(write(post(path),alice,original)).andExpect(status().isCreated())
                .andExpect(jsonPath("$.entries[0].quantity").value(1)).andReturn().getResponse();
        var deck=json.readTree(result.getContentAsByteArray());
        String owned=path+"/"+deck.get("id").asLong(),publicLink="/api/v1/shared/decks/"+deck.get("shareToken").asText();
        api.perform(get(publicLink)).andExpect(status().isOk()).andExpect(jsonPath("$.entries[0].name").value("공개 카드"));
        api.perform(as(get(owned),bob)).andExpect(status().isNotFound());
        api.perform(as(get(owned+"/history"),bob)).andExpect(status().isNotFound());
        api.perform(as(get(owned+"/history/1"),bob)).andExpect(status().isNotFound());
        var edit=save(1,false,"DRAFT",new DeckRules.Line(second,"MAIN",2));
        api.perform(write(put(owned),bob,edit)).andExpect(status().isNotFound());
        api.perform(write(put(owned),alice,edit)).andExpect(status().isOk()).andExpect(jsonPath("$.revision").value(2));
        api.perform(write(put(owned),alice,edit)).andExpect(status().isConflict());
        api.perform(as(get(owned+"/history"),alice)).andExpect(jsonPath("$.total").value(2));
        api.perform(as(get(owned+"/history/1"),alice)).andExpect(jsonPath("$.entries[0].cardId").value(first));
        api.perform(get(publicLink)).andExpect(status().isNotFound());
        api.perform(as(get(path),bob)).andExpect(jsonPath("$.total").value(0));
    }
    @Test void rulesCountNamesAcrossPrintingsAndRejectInvalidSectionsAndGames() throws Exception {
        String path="/api/v1/me/decks";
        var same=save(0,false,"DRAFT",new DeckRules.Line(first,"MAIN",2),new DeckRules.Line(second,"SIDE",2));
        api.perform(write(post(path),alice,same)).andExpect(status().isUnprocessableEntity());
        for(var bad:List.of(save(0,false,"DRAFT",new DeckRules.Line(first,"RUNE",1)),
                save(0,false,"DRAFT",new DeckRules.Line(card("POKEMON","다른 게임","PUBLISHED"),"MAIN",1)),
                save(0,false,"COMPLETE",new DeckRules.Line(first,"MAIN",2)))){
            api.perform(write(post(path),alice,bad)).andExpect(status().isUnprocessableEntity());
        }
        var energy=card("POKEMON","기본 풀 에너지","PUBLISHED");
        var basic=card("POKEMON","기본 포켓몬","PUBLISHED");
        db.sql("update card set specs='{\"stage\":\"기본\",\"card_type\":\"포켓몬\"}' where id=?").param(basic).update();
        var legal=new DeckApi.Save("완성 덱","POKEMON","COMPLETE",0,false,List.of(
                new DeckRules.Line(energy,"MAIN",59),new DeckRules.Line(basic,"MAIN",1)));
        api.perform(write(post(path),alice,legal)).andExpect(status().isCreated()).andExpect(jsonPath("$.state").value("COMPLETE"));
    }
    @Test void atlasTilesAreReusedAndUnpublishedCardsCloseThePublicLink() throws Exception {
        long sheet=db.sql("insert into image_sheet(storage_key,cell_width,cell_height) values(?,300,438) returning id")
                .param("sheets/"+UUID.randomUUID()+".webp").query(Long.class).single();
        db.sql("insert into card_variant(card_id,sheet_id,col_idx,row_idx) values(?,?,2,1)").param(first).param(sheet).update();
        api.perform(write(put(binder(first)),alice,new BinderApi.Quantity(2,0))).andExpect(status().isOk());
        api.perform(as(get("/api/v1/me/binder"),alice)).andExpect(jsonPath("$.items[0].image.sheetId").value(sheet));
        var created=api.perform(write(post("/api/v1/me/decks"),alice,save(0,true,"DRAFT",new DeckRules.Line(first,"MAIN",1))))
                .andExpect(status().isCreated()).andExpect(jsonPath("$.entries[0].image.col").value(2)).andReturn().getResponse();
        String shared="/api/v1/shared/decks/"+json.readTree(created.getContentAsByteArray()).get("shareToken").asText();
        api.perform(get(shared)).andExpect(jsonPath("$.entries[0].image.row").value(1));
        db.sql("update card set status='PENDING' where id=?").param(first).update();
        api.perform(get(shared)).andExpect(status().isNotFound());
        api.perform(as(get("/api/v1/me/binder"),alice)).andExpect(jsonPath("$.items[0].image").doesNotExist());
    }
}
