package kr.tcghub;

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
@EnabledIfEnvironmentVariable(named="TCG_TEST_DB",matches="1")
@Transactional
class WikiCardIntegrationTest {
    @Autowired MockMvc api;
    @Autowired JdbcClient db;

    @Test void foreignCardsKeepTheirOriginalAndReviewWinsOverAnAutomaticReading() throws Exception {
        long id=db.sql("""
            insert into card(legacy_key,game_code,name,effect,number,specs,status,source_url)
            values ('catalog:WEISS:en:test-reading','WEISS','Card reading','Draw 2 cards.','QA-EN',
                '{"language":"en","type":"Character"}','PUBLISHED','https://en.ws-tcg.com/cardlist/')
            returning id
            """).query(Long.class).single();
        db.sql("update card_korean_reading set due_at=null,name='한국어 검색 검증',effect='카드 2장을 뽑는다.' where card_id=?").param(id).update();
        api.perform(get("/api/v1/cards/"+id)).andExpect(jsonPath("$.nameBasis").value("MACHINE_TRANSLATION"))
                .andExpect(jsonPath("$.effectBasis").value("MACHINE_TRANSLATION")).andExpect(jsonPath("$.effectLanguage").value("ko"));
        api.perform(get("/api/v1/cards").param("game","WEISS").param("q","한국어 검색 검증"))
                .andExpect(jsonPath("$.items[0].id").value(id));
        api.perform(get("/api/v1/cards/"+id).param("lang","en")).andExpect(jsonPath("$.effect").value("Draw 2 cards."));
        db.sql("insert into card_translation(card_id,lang,name,basis,source_url,version) values (?,'ko','검수 이름','PRINTED_NAME','https://en.ws-tcg.com/',1)").param(id).update();
        api.perform(get("/api/v1/cards/"+id)).andExpect(jsonPath("$.name").value("검수 이름"))
                .andExpect(jsonPath("$.nameBasis").value("PRINTED_NAME")).andExpect(jsonPath("$.effectBasis").value("MACHINE_TRANSLATION"));
        org.junit.jupiter.api.Assertions.assertTrue(db.sql("""
              select name_ko='검수 이름' and text_en='Draw 2 cards.' and name_ja is null
                  and translation_source#>>'{ko,name}'='REVIEWED_PRINTING'
                  from catalog_localized_printing where card_id=?
              """).param(id).query(Boolean.class).single());
        db.sql("update card set effect='Draw 3 cards.' where id=?").param(id).update();
        api.perform(get("/api/v1/cards/"+id)).andExpect(jsonPath("$.effect").value("Draw 3 cards.")).andExpect(jsonPath("$.effectLanguage").value("en"));
    }

    @Test void matchedIdentitySuppliesOnlyMissingKoreanNameAndKeepsEvidenceSeparate() throws Exception {
        db.sql("""
                insert into wiki_card_document(game_code,lookup_key,passcode,title,document_url,snapshot_date,snapshot_url,
                    verification_url,names,facts) values('YUGIOH','cid:989879','777778','검사 표본','https://namu.wiki/w/검사%20표본',
                    '2021-03-01','https://example.org/snapshot','https://www.db.yugioh-card.com/?cid=989879',
                    '{"ko":"위키 이름 검증 표본"}','{"atk":0}')
                """).update();
        long id=db.sql("""
                insert into card(legacy_key,game_code,name,original_name,number,specs,status)
                values('catalog:YUGIOH:wiki-integration','YUGIOH','Fixture','Fixture','TST-EN000',
                    '{"konami_id":989879,"passcode":777778,"language":"en","wikiReferences":[{"title":"injected"}]}','PUBLISHED') returning id
                """).query(Long.class).single();
        api.perform(get("/api/v1/cards/"+id)).andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value("위키 이름 검증 표본")).andExpect(jsonPath("$.language").value("ko"))
                .andExpect(jsonPath("$.nameBasis").value("WIKI_REFERENCE")).andExpect(jsonPath("$.effect").isEmpty())
                .andExpect(jsonPath("$.specs.wikiReferences.length()").value(1))
                .andExpect(jsonPath("$.specs.wikiReferences[0].facts.atk").value(0))
                .andExpect(jsonPath("$.specs.wikiReferences[0].title").value("검사 표본"));
        api.perform(get("/api/v1/play/cards").param("game","YUGIOH").param("q","위키 이름 검증 표본"))
                .andExpect(jsonPath("$[0].id").value(id)).andExpect(jsonPath("$[0].nameBasis").value("WIKI_REFERENCE"));
        api.perform(get("/api/v1/cards/"+id).param("lang","en")).andExpect(jsonPath("$.name").value("Fixture"))
                .andExpect(jsonPath("$.language").value("en"));
        db.sql("update card set specs=specs||'{\"names\":{\"ko\":\"공식 이름\"}}'::jsonb where id=?").param(id).update();
        api.perform(get("/api/v1/cards/"+id)).andExpect(jsonPath("$.name").value("공식 이름"));
        db.sql("update card set specs=specs||'{\"passcode\":123}'::jsonb where id=?").param(id).update();
        api.perform(get("/api/v1/cards/"+id)).andExpect(jsonPath("$.specs.wikiReferences").doesNotExist());
    }
}
