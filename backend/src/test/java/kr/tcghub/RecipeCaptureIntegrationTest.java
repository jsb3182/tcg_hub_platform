package kr.tcghub;

import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.annotation.Transactional;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
@Transactional
@EnabledIfEnvironmentVariable(named="TCG_TEST_DB",matches="1")
class RecipeCaptureIntegrationTest {
    @Autowired MockMvc api;
    @Autowired JdbcClient db;
    @Autowired DeckApi decks;
    @Autowired DeckExportApi exports;
    private final UUID fixture = UUID.randomUUID();

    @Test void externalSelectionKeepsOnlyAManifestMatchedPrintingAcrossSharingExportAndCode() throws Exception {
        var owner = (java.security.Principal) () -> "recipe-" + fixture + "@example.invalid";
        db.sql("insert into app_user(email,password_hash) values(?,'unused')").param(owner.getName()).update();
        long card = card("YUGIOH","PUBLISHED","4041");
        db.sql("update card set number=cast(id as text) where id=?").param(card).update();
        var local = variant(card,sheet(false),0);
        var save = new DeckApi.Save("두 일러스트","YUGIOH","DRAFT",0,true,java.util.List.of(
                new DeckRules.Line(card,"MAIN",1,null,1),new DeckRules.Line(card,"MAIN",1,null,2),
                new DeckRules.Line(card,"MAIN",1,local)));
        var result = decks.create(owner, save);
        var reopened = decks.get(owner,result.deck().id(),"ko");
        var shared = decks.shared(result.deck().shareToken(),"ko");
        for (var details : java.util.List.of(result,reopened,shared)) {
            org.junit.jupiter.api.Assertions.assertEquals(1,details.entries().get(0).neuronArtwork());
            org.junit.jupiter.api.Assertions.assertEquals(2,details.entries().get(1).neuronArtwork());
            org.junit.jupiter.api.Assertions.assertNull(details.entries().get(1).image());
            org.junit.jupiter.api.Assertions.assertEquals("https://artworks-jp-n.ygoresources.com/0/40/41_2.png",
                    details.entries().get(1).imageUrl());
            org.junit.jupiter.api.Assertions.assertEquals(local,details.entries().get(2).variantId());
        }
        var backup=exports.page(owner,0).items().get(0);
        org.junit.jupiter.api.Assertions.assertEquals(2,backup.entries().get(1).neuronArtwork());
        var replay=decks.importCode(owner,decks.code(owner,result.deck().id()));
        org.junit.jupiter.api.Assertions.assertEquals(reopened.entries(),replay.entries());
        api.perform(get("/api/v1/cards/capture-identities").param("ids","4041"))
                .andExpect(status().isOk()).andExpect(jsonPath("$[0].artworks['2']").value(
                        "https://artworks-jp-n.ygoresources.com/0/40/41_2.png"));
    }
    @Test void validationRejectsWrongCidAndMixedLocalAndOfficialArtwork() {
        var owner=(java.security.Principal) () -> "recipe-" + fixture + "@example.invalid";
        db.sql("insert into app_user(email,password_hash) values(?,'unused')").param(owner.getName()).update();
        long card=card("YUGIOH","PUBLISHED","90009999");
        long variant=variant(card,sheet(false),0);
        var invalid=new DeckApi.Save("검증","YUGIOH","DRAFT",0,false,java.util.List.of(new DeckRules.Line(card,"MAIN",1,null,2)));
        org.junit.jupiter.api.Assertions.assertThrows(DeckRules.Invalid.class,()->decks.create(owner,invalid));
        var mixed=new DeckApi.Save("검증","YUGIOH","DRAFT",0,false,java.util.List.of(new DeckRules.Line(card,"MAIN",1,variant,1)));
        org.junit.jupiter.api.Assertions.assertThrows(DeckRules.Invalid.class,()->decks.create(owner,mixed));
    }

    private long card(String game, String state, String cid) {
        return db.sql("""
                INSERT INTO card(game_code,name,number,specs,status) VALUES (?,'capture fixture','F1',
                    jsonb_build_object('konami_id',?::text,'type','Monster','names',jsonb_build_object('ko','시험판')),?)
                RETURNING id
                """).param(game).param(cid).param(state).query(Long.class).single();
    }
    private long sheet(boolean retired) {
        String hash = UUID.randomUUID().toString().replace("-","").repeat(2);
        return db.sql("INSERT INTO image_sheet(storage_key,cell_width,cell_height,retired) VALUES (?,48,70,?) RETURNING id")
                .param("sheets/"+hash+".webp").param(retired).query(Long.class).single();
    }
    private long variant(long card,long sheet,int position) {
        return db.sql("INSERT INTO card_variant(card_id,position,sheet_id,col_idx,row_idx) VALUES (?,?,?,2,1) RETURNING id")
                .param(card).param(position).param(sheet).query(Long.class).single();
    }
    @Test void indexUsesOnlyPublishedYugiohAndCurrentImages() throws Exception {
        long id = card("YUGIOH","PUBLISHED","90000001");
        long active = sheet(false);
        long art = variant(id,active,2);
        variant(card("YUGIOH","PENDING","90000002"),sheet(false),0);
        variant(card("POKEMON","PUBLISHED","90000003"),sheet(false),0);
        variant(id,sheet(true),3);
        api.perform(get("/api/v1/cards/capture-index").param("after",Long.toString(art-1)))
                .andExpect(status().isOk()).andExpect(jsonPath("$.items.length()").value(1))
                .andExpect(jsonPath("$.items[0].cardId").value(id)).andExpect(jsonPath("$.items[0].variantId").value(art))
                .andExpect(jsonPath("$.items[0].artworkIndex").value(3)).andExpect(jsonPath("$.items[0].name").value("시험판"))
                .andExpect(jsonPath("$.items[0].konamiId").value("90000001")).andExpect(jsonPath("$.items[0].image.col").value(2))
                .andExpect(jsonPath("$.next").isEmpty());
        api.perform(get("/api/v1/cards/capture-index").param("after",Long.toString(art)))
                .andExpect(status().isOk()).andExpect(jsonPath("$.items.length()").value(0));
        api.perform(get("/api/v1/cards/capture-index").param("after","-1")).andExpect(status().isBadRequest());
    }
    @Test void identitiesResolveOnlyPublishedCardsWithANumericKey() throws Exception {
        long first = card("YUGIOH","PUBLISHED","90000001");
        card("YUGIOH","PUBLISHED","90000001");
        card("YUGIOH","PENDING","90000002");
        card("POKEMON","PUBLISHED","90000003");
        api.perform(get("/api/v1/cards/capture-identities").param("ids","90000001,90000002,90000001,90000003"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.length()").value(1))
                .andExpect(jsonPath("$[0].konamiId").value("90000001")).andExpect(jsonPath("$[0].cardId").value(first))
                .andExpect(jsonPath("$[0].name").value("시험판")).andExpect(jsonPath("$[0].variantId").doesNotExist());
        api.perform(get("/api/v1/cards/capture-identities").param("ids","1,2,b"))
                .andExpect(status().isBadRequest());
        api.perform(get("/api/v1/cards/capture-identities").param("ids","1,".repeat(100)+"1"))
                .andExpect(status().isBadRequest());
    }
}
