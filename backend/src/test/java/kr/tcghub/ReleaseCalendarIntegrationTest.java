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

@SpringBootTest @AutoConfigureMockMvc @Transactional
@EnabledIfEnvironmentVariable(named="TCG_TEST_DB",matches="1")
class ReleaseCalendarIntegrationTest {
    @Autowired MockMvc api;
    @Autowired JdbcClient db;
    private static final String URL="/api/v1/release-calendar";
    private long event(String key,String region,String day) {
        return db.sql("""
            insert into product_release(game_code,product_key,region,name,names,release_date,source_url,catalog_code)
            values('POKEMON',?,?,'Calendar QA','{"ko":"지역일정검증","en":"Regional Calendar QA"}',
                   cast(? as date),'https://example.invalid/test','QA-V35') returning id
            """).param(key).param(region).param(day).query(Long.class).single();
    }

    @Test void publicCalendarFiltersBeforePagingAndKeepsRegionalDatesSeparate() throws Exception {
        long last=event("same","KR","2089-01-03");
        long first=event("same","JP","2089-01-02");
        event("past","KR","2000-01-01");
        api.perform(get(URL).param("game","POKEMON").param("q","지역일정검증").param("size","1"))
            .andExpect(status().isOk()).andExpect(jsonPath("$.total").value(2)).andExpect(jsonPath("$.items[0].id").value(first))
            .andExpect(jsonPath("$.asOf").isString());
        api.perform(get(URL).param("q","regional calendar qa").param("size","1").param("page","1"))
            .andExpect(jsonPath("$.items[0].id").value(last)).andExpect(jsonPath("$.items[0].region").value("KR"));
        api.perform(get(URL).param("q","지역일정검증").param("period","past").param("region","KR"))
            .andExpect(jsonPath("$.total").value(1)).andExpect(jsonPath("$.items[0].releaseDate").value("2000-01-01"));
        api.perform(get(URL).param("q","지역일정검증").param("period","all").param("page","999"))
            .andExpect(jsonPath("$.total").value(3)).andExpect(jsonPath("$.items").isEmpty());
        api.perform(get(URL).param("game","other")).andExpect(status().isBadRequest());
        api.perform(get(URL).param("size","101")).andExpect(status().isBadRequest());
    }

    @Test void linksOnlyAnUnambiguousCatalogProductAndCountsOnlyPublishedCards() throws Exception {
        long event=event("linked","KR","2089-01-02");
        long pack=db.sql("""
            insert into pack(game_code,code,name,legacy_key)
            values('POKEMON','QA-V35','test','catalog:POKEMON:v35-a') returning id
            """).query(Long.class).single();
        db.sql("insert into card(game_code,pack_id,name,status) values('POKEMON',?,'one','PUBLISHED'),('POKEMON',?,'two','PENDING')")
            .param(pack).param(pack).update();
        api.perform(get(URL).param("packId",""+pack).param("period","all")).andExpect(status().isOk())
            .andExpect(jsonPath("$.items[0].id").value(event)).andExpect(jsonPath("$.items[0].catalogPackId").value(pack))
            .andExpect(jsonPath("$.items[0].catalogCount").value(1));
        db.sql("insert into pack(game_code,code,name,legacy_key) values('POKEMON','QA-V35','other','catalog:POKEMON:v35-b')").update();
        api.perform(get(URL).param("q","지역일정검증")).andExpect(jsonPath("$.items[0].catalogPackId").isEmpty())
            .andExpect(jsonPath("$.items[0].catalogCount").value(0));
        api.perform(get(URL).param("packId",""+pack).param("period","all")).andExpect(jsonPath("$.total").value(0));
        api.perform(get(URL).param("q","MZMC").param("game","YUGIOH").param("period","all"))
            .andExpect(jsonPath("$.items[0].catalogPackId").isNumber()).andExpect(jsonPath("$.items[0].region").value("NA"));
    }

    @Test void onePieceRegionalCalendarTitleAndPreviousPackUrlResolveToTheSamePrintings() throws Exception {
        long pack=db.sql("""
            insert into pack(game_code,code,name,legacy_key) values('ONEPIECE','OP-98','Fixture base','catalog:ONEPIECE:OP-98') returning id
            """).query(Long.class).single();
        long previous=db.sql("""
            insert into pack(game_code,code,name,legacy_key,superseded_by)
            values('ONEPIECE','OP-98','별도 수록 이름',onepiece_numbered_pack_key('OP-98'),?) returning id
            """).param(pack).query(Long.class).single();
        db.sql("insert into onepiece_pack_label(pack_id,name) values(?,'별도 수록 이름')").param(pack).update();
        db.sql("insert into card(game_code,pack_id,name,status) values('ONEPIECE',?,'Fixture card','PUBLISHED')").param(pack).update();
        db.sql("""
            insert into product_release(game_code,product_key,region,name,release_date,source_url,catalog_code,catalog_name,manual,selected_pack_id)
            values('ONEPIECE','fixture:regional','KR','Fixture regional','2089-02-03','https://example.invalid','OP-98','별도 수록 이름',false,null),
                  ('ONEPIECE','fixture:selected','KR','Fixture manual','2089-02-02','https://example.invalid',null,null,true,?)
            """).param(previous).update();
        for (long id : new long[]{pack,previous}) {
            api.perform(get(URL).param("packId",String.valueOf(id)).param("period","all"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.total").value(2))
                .andExpect(jsonPath("$.items[0].catalogPackId").value(pack)).andExpect(jsonPath("$.items[0].catalogCount").value(1))
                .andExpect(jsonPath("$.items[1].catalogPackId").value(pack));
        }
        db.sql("insert into pack(game_code,code,name,legacy_key) values('ONEPIECE','OP-98','별도 수록 이름','catalog:ONEPIECE:unrelated-fixture')").update();
        api.perform(get(URL).param("packId",String.valueOf(pack)).param("period","all"))
            .andExpect(jsonPath("$.total").value(1)).andExpect(jsonPath("$.items[0].productKey").value("fixture:selected"));
    }
}
