package kr.tcghub;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.annotation.Transactional;
import static org.assertj.core.api.Assertions.assertThat;
import static org.hamcrest.Matchers.hasItem;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
@EnabledIfEnvironmentVariable(named="TCG_TEST_DB",matches="1")
@Transactional
class CatalogFacetIntegrationTest {
    @Autowired MockMvc api;
    @Autowired JdbcClient db;

    @Test void yearAndColorSelectThePrintingAndReturnToItsDetails() throws Exception {
        long pack=db.sql("""
            insert into pack(game_code,code,name,legacy_key) values ('ONEPIECE','QA-3044','색상 검색 검사','catalog:ONEPIECE:test-search')
            returning id
            """).query(Long.class).single();
        db.sql("""
            insert into product_release(game_code,product_key,region,name,release_date,source_url,catalog_code)
            values ('ONEPIECE','qa-3044','KR','검사 상품','2024-07-01','https://example.org','QA-3044')
            """).update();
        long id=db.sql("""
            insert into card(game_code,pack_id,name,number,specs,status) values ('ONEPIECE',?,'검사 캐릭터','QA-3044-A',
                '{"colors":["red","blue"],"cost":0,"language":"ko"}','PUBLISHED') returning id
            """).param(pack).query(Long.class).single();
        db.sql("""
            insert into card(game_code,pack_id,name,number,specs,status,release_date) values
               ('ONEPIECE',?,'검사 캐릭터','QA-3044-B','{"colors":["red"]}','PUBLISHED','2025-01-01'),
               ('ONEPIECE',?,'검사 캐릭터','QA-3044-C','{"colors":["green"]}','PENDING','2099-01-01')
            """).param(pack).param(pack).update();
        api.perform(get("/api/v1/cards").param("game","ONEPIECE").param("q","QA-3044")
                .param("releaseYear","2024").param("traitKey","color").param("traitValue","red"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.total").value(1))
                .andExpect(jsonPath("$.items[0].id").value(id)).andExpect(jsonPath("$.items[0].productReleaseDate").value("2024-07-01"));
        api.perform(get("/api/v1/cards/"+id)).andExpect(jsonPath("$.releaseDate").isEmpty())
                .andExpect(jsonPath("$.productReleaseDate").value("2024-07-01"));
        api.perform(get("/api/v1/cards/facets").param("game","ONEPIECE").param("traitKey","color"))
                .andExpect(jsonPath("$.years",hasItem(2024))).andExpect(jsonPath("$.values",hasItem("blue")));
        api.perform(get("/api/v1/cards").param("game","POKEMON").param("traitKey","race").param("traitValue","Dragon"))
                .andExpect(status().isBadRequest());
        api.perform(get("/api/v1/cards").param("game","WEISS").param("traitKey","soul")).andExpect(status().isBadRequest());
    }

    @Test void existingLegacyAndRegionalDataHaveEquivalentFilters() {
        assertThat(db.sql("select catalog_trait_values('YUGIOH','{\"rc\":\"드래곤족\"}','race')=array['Dragon']").query(Boolean.class).single()).isTrue();
        assertThat(db.sql("select catalog_trait_values('YUGIOH','{\"lv\":4,\"sub\":\"엑시즈 / 효과\"}','level')='{}'").query(Boolean.class).single()).isTrue();
        assertThat(db.sql("select catalog_trait_values('YUGIOH','{\"lv\":4,\"sub\":\"엑시즈 / 효과\"}','rank')=array['4']").query(Boolean.class).single()).isTrue();
        assertThat(db.sql("select catalog_trait_values('NIVEL','{\"코스트\":0}','cost')=array['0']").query(Boolean.class).single()).isTrue();
        assertThat(db.sql("select catalog_trait_values('POKEMON','{\"types\":[\"풀\",\"악\"]}','energyType') @> array['풀','악']").query(Boolean.class).single()).isTrue();
        assertThat(db.sql("select catalog_trait_values('WEISS','{\"color\":\"Red\"}','color')=array['Red']").query(Boolean.class).single()).isTrue();
        assertThat(db.sql("select catalog_trait_values('RIFTBOUND','{\"domains\":[\"Fury\"]}','domain')=array['Fury']").query(Boolean.class).single()).isTrue();
        assertThat(db.sql("select catalog_print_traits('ONEPIECE','{\"regionalFacts\":{\"ko\":{\"attribute\":\"참격/특수\"}}}','attribute')=array['참격','특수']").query(Boolean.class).single()).isTrue();
    }

    @Test void indexFollowsPublicationRulesAndCardChanges() {
        long card=db.sql("""
            insert into card(game_code,name,status,specs) values ('YUGIOH','facet test','PENDING',
                '{"rc":"드래곤족","lv":4,"sub":"엑시즈 / 효과"}') returning id
            """).query(Long.class).single();
        String lookup="select facets::text from catalog_search_cache where card_id=?";
        assertThat(db.sql(lookup).param(card).query(String.class).optional()).isEmpty();
        db.sql("update card set status='PUBLISHED' where id=?").param(card).update();
        assertThat(db.sql(lookup).param(card).query(String.class).single()).contains("Dragon","rank","4").doesNotContain("level");
        db.sql("update card set specs=jsonb_set(specs,'{rc}','\"전사족\"') where id=?").param(card).update();
        assertThat(db.sql(lookup).param(card).query(String.class).single()).contains("Warrior").doesNotContain("Dragon");
        db.sql("update card set status='REJECTED' where id=?").param(card).update();
        assertThat(db.sql(lookup).param(card).query(String.class).optional()).isEmpty();
    }
}
