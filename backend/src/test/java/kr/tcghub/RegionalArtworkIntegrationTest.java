package kr.tcghub;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.annotation.Transactional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
@EnabledIfEnvironmentVariable(named="TCG_TEST_DB",matches="1")
@Transactional
class RegionalArtworkIntegrationTest {
    @Autowired JdbcClient db;
    @Autowired MockMvc http;

    @Test void manifestRegionsAreDistinctAndExactPrintingWins() throws Exception {
        long pack=db.sql("insert into pack(game_code,name) values('YUGIOH','Reference edition test') returning id")
                .query(Long.class).single();
        long card=db.sql("""
            insert into card(game_code,pack_id,name,specs,status) values ('YUGIOH',?,'Reference test',
            '{"language":"en","konami_id":4041,"images":{"en":"https://example.org/exact.png"},
              "imageSources":{"en":"https://example.org/print"},"imageProducts":{"en":"TST"}}','PUBLISHED') returning id
            """).param(pack).query(Long.class).single();
        String kr="https://artworks-ko-db.ygoresources.com/0/40/41_1.png";
        http.perform(get("/api/v1/cards/"+card).param("lang","ko")).andExpect(status().isOk())
                .andExpect(header().string("Content-Security-Policy",
                        org.hamcrest.Matchers.matchesPattern(".*img-src [^;]*https://cmsassets\\.rgpub\\.io(?: [^;]*)?;.*")))
                .andExpect(jsonPath("$.imageBasis").value("CARD_REFERENCE")).andExpect(jsonPath("$.imageLanguage").value("ko"))
                .andExpect(jsonPath("$.imageUrl").value(kr)).andExpect(jsonPath("$.imageSource").value(kr))
                .andExpect(jsonPath("$.imageProduct").isEmpty());
        http.perform(get("/api/v1/packs/"+pack).param("lang","ja")).andExpect(status().isOk())
                .andExpect(jsonPath("$.cards[0].imageUrl").value("https://artworks-jp-n.ygoresources.com/0/40/41_1.png"))
                .andExpect(jsonPath("$.cards[0].imageBasis").value("CARD_REFERENCE"));
        http.perform(get("/api/v1/play/cards").param("game","YUGIOH").param("ids",Long.toString(card)).param("lang","en"))
                .andExpect(jsonPath("$[0].imageUrl").value("https://example.org/exact.png"))
                .andExpect(jsonPath("$[0].imageProduct").value("TST")).andExpect(jsonPath("$[0].imageBasis").isEmpty());
    }

    @Test void aMissingEditionUsesItsRealLanguageAndRushIsAbsent() throws Exception {
        assertEquals(0L,db.sql("select count(*) from yugioh_reference_art where cid='15150'").query(Long.class).single());
        String cid=db.sql("select cid from yugioh_reference_art where ko_path is null and en_path is null and ja_path is not null limit 1")
                .query(String.class).single();
        long id=db.sql("""
            insert into card(game_code,name,specs,status) values ('YUGIOH','Japanese reference',
                jsonb_build_object('konami_id',cast(? as text)),'PUBLISHED') returning id
            """).param(cid).query(Long.class).single();
        http.perform(get("/api/v1/cards/"+id).param("lang","ko")).andExpect(status().isOk())
                .andExpect(jsonPath("$.imageLanguage").value("ja")).andExpect(jsonPath("$.imageBasis").value("CARD_REFERENCE"));
        db.sql("update card set game_code='POKEMON' where id=?").param(id).update();
        http.perform(get("/api/v1/cards/"+id).param("lang","ko")).andExpect(jsonPath("$.imageUrl").isEmpty());
    }
}
