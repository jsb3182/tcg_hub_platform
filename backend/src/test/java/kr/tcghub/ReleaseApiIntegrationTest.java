package kr.tcghub;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.stream.StreamSupport;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.annotation.Transactional;
import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
@EnabledIfEnvironmentVariable(named="TCG_TEST_DB", matches="1")
@Transactional
class ReleaseApiIntegrationTest {
    @Autowired MockMvc api;
    @Autowired JdbcClient db;
    @Autowired ObjectMapper json;

    private long pack(String name, String key, String metadata) {
        return db.sql("insert into pack(game_code,name,legacy_key,metadata) values('YUGIOH',?,?,cast(? as jsonb)) returning id")
                .param(name).param(key).param(metadata).query(Long.class).single();
    }

    @Test void calendarUsesPublishedPrintingsAndDistinguishesTheFourSections() throws Exception {
        long schedule = pack("Announced pack","legacy:release-test-schedule","{}");
        long section = pack("Test promos","legacy:release-test-distribution",
                "{\"sec\":true,\"sx\":\"e\",\"kind\":\"동봉\",\"note\":\"일정\",\"privateNote\":\"not public\"}");
        long premiere = pack("World premiere","legacy:release-test-premiere","{\"sec\":true,\"wp\":true}");
        long archive = pack("Archive","legacy:release-test-archive","{\"sec\":true,\"sx\":\"l\"}");
        long undated = pack("Ordinary source set","catalog:release-test-undated","{}");
        long dated = db.sql("insert into pack(game_code,name,release_date) values('POKEMON','Dated pack','2026-12-01') returning id")
                .query(Long.class).single();
        db.sql("""
                insert into card(game_code,pack_id,name,status,specs)
                select 'YUGIOH',?,name,status,specs::jsonb from (values
                  ('first','PUBLISHED','{"nw":"신규","pr":"Promo A","pd":"2025-02-08"}'),
                  ('second','PUBLISHED','{"nw":"재록","pr":"Promo A","pd":"2025-03"}'),
                  ('third','PUBLISHED','{"nw":"신규 일러스트","pr":"Promo B","pd":"2025-03"}'),
                  ('unknown','PUBLISHED','{}'),('pending','PENDING','{"nw":"신규","pr":"Hidden","pd":"2029-01"}'),
                  ('rejected','REJECTED','{"nw":"재록"}')
                ) v(name,status,specs)
                """).param(section).update();

        JsonNode rows=json.readTree(api.perform(get("/api/v1/releases")).andExpect(status().isOk())
                .andReturn().getResponse().getContentAsByteArray());
        var byId=StreamSupport.stream(rows.spliterator(),false).collect(java.util.stream.Collectors.toMap(
                n -> n.path("id").asLong(), n -> n));
        assertEquals("SCHEDULE",byId.get(schedule).path("group").asText());
        assertEquals(0,byId.get(schedule).path("total").asInt());
        assertEquals("SCHEDULE",byId.get(dated).path("group").asText());
        assertEquals("PREMIERE",byId.get(premiere).path("group").asText());
        assertEquals("ARCHIVE",byId.get(archive).path("group").asText());
        assertFalse(byId.containsKey(undated));
        JsonNode row=byId.get(section);
        assertEquals("DISTRIBUTION",row.path("group").asText());
        assertEquals("일정",row.path("metadata").path("note").asText());
        assertFalse(row.path("metadata").has("privateNote"));
        assertEquals(4,row.path("total").asInt());
        for(String key: new String[]{"newCount","reprintCount","newArtCount"}) assertEquals(1,row.path(key).asInt());
        assertEquals(2,row.path("productCount").asInt());
        assertEquals("2025-02-08",row.path("firstProductDate").asText());
        assertEquals("2025-03",row.path("lastProductDate").asText());
        assertEquals("Promo B",row.path("latestProduct").asText());
    }

    @Test void premiereAnnouncementSeparatesNorthAmericanProductFactsFromCataloguedPrintings() throws Exception {
        long id=db.sql("""
                select id from pack where game_code='YUGIOH' and code='MZMC' and metadata @> '{"sec":true,"wp":true}'
                """).query(Long.class).single();
        var pack=json.readTree(api.perform(get("/api/v1/packs/"+id)).andExpect(status().isOk())
                .andExpect(jsonPath("$.group").value("PREMIERE"))
                .andExpect(jsonPath("$.officialProduct.englishName").value("Maze of Machines"))
                .andExpect(jsonPath("$.officialProduct.setSize").value(153))
                .andExpect(jsonPath("$.officialProduct.otsDate").value("2027-03-17"))
                .andExpect(jsonPath("$.officialProduct.launchDate").value("2027-03-19"))
                .andExpect(jsonPath("$.officialProduct.sourceUrl").value("https://www.yugioh-card.com/en/products/mzmc/"))
                .andReturn().getResponse().getContentAsByteArray());
        assertEquals(db.sql("select count(*) from card where pack_id=? and status='PUBLISHED'").param(id)
                .query(Long.class).single().longValue(),pack.path("total").asLong());
        long other=db.sql("insert into pack(game_code,code,name) values('YUGIOH','MZMC','Separate product listing') returning id")
                .query(Long.class).single();
        api.perform(get("/api/v1/packs/"+other)).andExpect(jsonPath("$.officialProduct").isEmpty());
    }

    @Test void boundedDetailReturnsLocalizedCardsAndDoesNotSplitEnglishRarityNames() throws Exception {
        long pack=pack("Detail pack","legacy:release-test-detail","{}");
        long first=db.sql("""
                insert into card(legacy_key,game_code,pack_id,number,name,original_name,rarity,specs,status)
                values('legacy:release-test:1','YUGIOH',?,'T-001','이름','原名','UR SE',
                    '{"nw":"재록","k":"마법","sub":"속공","pd":"2026-02-01","pr":"February product"}','PUBLISHED') returning id
                """).param(pack).query(Long.class).single();
        db.sql("""
                insert into legacy_card_edition(card_id,matched_number,matched_name,names,texts,source_url)
                values(?,'T-001','原名','{"en":"Printed name"}','{"en":"Printed rule"}','https://example.test/edition')
                """).param(first).update();
        db.sql("insert into card_variant(card_id,position,rarity) values(?,0,'UR SE'),(?,1,'PSE')").param(first).param(first).update();
        db.sql("insert into card(game_code,pack_id,name,rarity,status) values('YUGIOH',?,'Other','Ultra Rare','PUBLISHED')")
                .param(pack).update();
        db.sql("insert into card(game_code,pack_id,name,status) values('YUGIOH',?,'Pending','PENDING')").param(pack).update();
        String url="/api/v1/packs/"+pack;
        api.perform(get(url).param("lang","en").param("size","1"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.id").value(pack)).andExpect(jsonPath("$.total").value(2))
                .andExpect(jsonPath("$.page").value(0)).andExpect(jsonPath("$.size").value(1)).andExpect(jsonPath("$.hasMore").value(true))
                .andExpect(jsonPath("$.cards[0].name").value("Printed name")).andExpect(jsonPath("$.cards[0].language").value("en"))
                .andExpect(jsonPath("$.cards[0].effect").value("Printed rule")).andExpect(jsonPath("$.cards[0].effectLanguage").value("en"))
                .andExpect(jsonPath("$.cards[0].inclusion").value("REPRINT")).andExpect(jsonPath("$.cards[0].type").value("마법"))
                .andExpect(jsonPath("$.cards[0].subtype").value("속공")).andExpect(jsonPath("$.cards[0].product").value("February product"))
                .andExpect(jsonPath("$.cards[0].variantCount").value(2)).andExpect(jsonPath("$.cards[0].rarities.length()").value(3))
                .andExpect(jsonPath("$.cards[0].rarities[2]").value("PSE"));
        api.perform(get(url).param("size","1").param("page","1"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.hasMore").value(false))
                .andExpect(jsonPath("$.cards[0].name").value("Other")).andExpect(jsonPath("$.cards[0].rarities[0]").value("Ultra Rare"))
                .andExpect(jsonPath("$.cards[0].inclusion").isEmpty());
        api.perform(get(url).param("size","201")).andExpect(status().isBadRequest());
        api.perform(get(url).param("lang","ru")).andExpect(status().isBadRequest());
        api.perform(get("/api/v1/packs/9223372036854775807")).andExpect(status().isNotFound());
        api.perform(get("/releases")).andExpect(forwardedUrl("/index.html"));
        api.perform(get("/releases/"+pack)).andExpect(forwardedUrl("/index.html"));
    }
}
