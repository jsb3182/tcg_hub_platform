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
@EnabledIfEnvironmentVariable(named="TCG_TEST_DB", matches="1")
class YugiohKoreanPrintingTest {
    @Autowired JdbcClient db;
    @Autowired MockMvc api;

    @Test void onlyTrustedIdentityExposesKoreanPrintingAndItsOptionalProductDate() throws Exception {
        int cid = 999999923;
        db.sql("""
            insert into yugioh_korean_print values(?, 'LOB-K119', repeat('a',40), '55144522.json',
              '2003-12-09', '240fad99-f00a-41ed-99e9-26656d0d677c')
            """).param(cid).update();
        var id = db.sql("""
            insert into card(game_code,name,original_name,number,status,legacy_key,source_id,specs)
            select 'YUGIOH','Test card','Original','EX-001','PUBLISHED',?,id,
                   jsonb_build_object('konami_id',cast(? as integer),'koreanPrinting','bad input')
              from feed_source where source_key='YUGIOH' and provider='CATALOG' returning id
            """).param("catalog:YUGIOH:"+UUID.randomUUID()).param(cid).query(Long.class).single();
        String uri = "/api/v1/cards/" + id;
        api.perform(get(uri)).andExpect(status().isOk())
            .andExpect(jsonPath("$.number").value("EX-001"))
            .andExpect(jsonPath("$.specs.koreanPrinting.number").value("LOB-K119"))
            .andExpect(jsonPath("$.specs.koreanPrinting.productReleasedOn").value("2003-12-09"))
            .andExpect(jsonPath("$.specs.koreanPrinting.cardUrl").value(org.hamcrest.Matchers.endsWith("cid="+cid)))
            .andExpect(jsonPath("$.specs.koreanPrinting.productSourceUrl").value(org.hamcrest.Matchers.endsWith("240fad99-f00a-41ed-99e9-26656d0d677c.json")));
        db.sql("update card set source_id=null,legacy_key=null where id=?").param(id).update();
        api.perform(get(uri)).andExpect(jsonPath("$.specs.koreanPrinting").doesNotExist());
        db.sql("update card set legacy_key=? where id=?").param("legacy:"+UUID.randomUUID()).param(id).update();
        db.sql("""
            insert into legacy_card_edition(card_id,matched_number,matched_name,names,texts,source_url,konami_id)
              values(?,'EX-001','Original','{}','{}','https://example.invalid',?)
            """).param(id).param(cid).update();
        db.sql("update yugioh_korean_print set product_released_on=null,product_id=null where konami_id=?").param(cid).update();
        api.perform(get(uri)).andExpect(jsonPath("$.specs.koreanPrinting.number").value("LOB-K119"))
            .andExpect(jsonPath("$.specs.koreanPrinting.productReleasedOn").doesNotExist())
            .andExpect(jsonPath("$.specs.koreanPrinting.productSourceUrl").doesNotExist());
        db.sql("update card set number='corrected' where id=?").param(id).update();
        api.perform(get(uri)).andExpect(jsonPath("$.specs.koreanPrinting").doesNotExist());
    }
}
