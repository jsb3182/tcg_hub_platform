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
@EnabledIfEnvironmentVariable(named="TCG_TEST_DB", matches="1")
@Transactional
class LegacyCardEditionIntegrationTest {
    @Autowired MockMvc api;
    @Autowired JdbcClient db;

    @Test void catalogAndPracticeResolveTheSamePrintingAndKeepCuratedText() throws Exception {
        String english = "Edition " + UUID.randomUUID();
        long id = db.sql("""
                insert into card(legacy_key,game_code,number,name,original_name,effect,specs,status)
                values(?,'YUGIOH','DBGV-JP001','한국어 이름','原名','원래 효과',
                  '{"texts":{"en":"Curated text"}}','PUBLISHED') returning id
                """).param("legacy:" + UUID.randomUUID()).query(Long.class).single();
        String source = "https://www.db.yugioh-card.com/yugiohdb/card_search.action?ope=2&cid=23532";
        db.sql("""
                insert into legacy_card_edition(card_id,matched_number,matched_name,names,texts,source_url,konami_id)
                values(?,'DBGV-JP001','原名',jsonb_build_object('en',cast(? as text),'ja','原名'),
                    '{"en":"Provider text","ja":"日本語の効果"}',?,23532)
                """).param(id).param(english).param(source).update();

        api.perform(get("/api/v1/cards").param("game","YUGIOH").param("lang","en").param("q",english).param("size","1"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.total").value(1))
                .andExpect(jsonPath("$.items[0].id").value(id)).andExpect(jsonPath("$.items[0].effect").value("Curated text"));
        api.perform(get("/api/v1/cards/" + id).param("lang","ja"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.name").value("原名"))
                .andExpect(jsonPath("$.effect").value("日本語の効果")).andExpect(jsonPath("$.effectLanguage").value("ja"))
                .andExpect(jsonPath("$.specs.names.en").value(english)).andExpect(jsonPath("$.specs.texts.en").value("Curated text"))
                .andExpect(jsonPath("$.sourceUrl").value(source));
        api.perform(get("/api/v1/play/cards").param("game","YUGIOH").param("lang","en").param("q",english))
                .andExpect(status().isOk()).andExpect(jsonPath("$[0].id").value(id))
                .andExpect(jsonPath("$[0].name").value(english)).andExpect(jsonPath("$[0].language").value("en"))
                .andExpect(jsonPath("$[0].effect").value("Curated text"));

        db.sql("update card set original_name='訂正後' where id=?").param(id).update();
        api.perform(get("/api/v1/cards/" + id).param("lang","ja"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.name").value("한국어 이름"))
                .andExpect(jsonPath("$.language").value("ko")).andExpect(jsonPath("$.effectLanguage").value("ko"))
                .andExpect(jsonPath("$.specs.names.en").doesNotExist()).andExpect(jsonPath("$.sourceUrl").isEmpty());
        api.perform(get("/api/v1/play/cards").param("game","YUGIOH").param("q",english))
                .andExpect(status().isOk()).andExpect(jsonPath("$.length()").value(0));
    }

    @Test void importedJapaneseOnlyEffectAndUnconfirmedNameAreLabeledIndependently() throws Exception {
        long id = db.sql("""
                insert into card(legacy_key,game_code,name,effect,specs,status)
                values(?,'YUGIOH','?','目を持つ竜。','{"ej":1}','PUBLISHED') returning id
                """).param("legacy:" + UUID.randomUUID()).query(Long.class).single();
        api.perform(get("/api/v1/play/cards").param("game","YUGIOH").param("lang","ko").param("ids",Long.toString(id)))
                .andExpect(status().isOk()).andExpect(jsonPath("$[0].name").value("?"))
                .andExpect(jsonPath("$[0].language").value("und")).andExpect(jsonPath("$[0].effectLanguage").value("ja"));
    }
}
