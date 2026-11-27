package kr.tcghub;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;
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

    @Test void wikiProductReferencesRequireTheExactCatalogEditionAndMarket() throws Exception {
        record Edition(String game, String code, String name, String date, String url, String hash) {}
        var editions = List.of(
                new Edition("RIFTBOUND", "OGN", "Origins", "2025-10-31",
                        "https://playriftbound.com/en-us/news/announcements/how-to-buy-riftbound/",
                        "12bbc81f1b2423158bf4807b87c8f35e525ebb6b8ac1786e1cd5dff3fc9eb935"),
                new Edition("RIFTBOUND", "UNL", "Unleashed", "2026-05-08",
                        "https://playriftbound.com/en-us/news/announcements/the-unleashed-overview/",
                        "ead1cbce54dee9bce1aaa6ee072a21fc7a090b018074990427e72ce3d5f9934d"),
                new Edition("WEISS", "SAO/S47", "Sword Art Online Re: Edit", "2017-04-28",
                        "https://en.ws-tcg.com/products/bp-sao-re/",
                        "b4d16e16e7c3747a6de3282a7b2425d2345bacdc55968b8a7a58ce3af98fc7e6"),
                new Edition("WEISS", "SAO/S80", "Sword Art Online -Alicization- Vol.2", "2021-11-05",
                        "https://en.ws-tcg.com/products/bp-sao-al2/",
                        "bab5af02e15b2d5e9aed25f1267604f467eab450d97e33a722cd976628a638a4")
        );
        for (var e : editions) {
            String prefix = "catalog:" + e.game() + ":";
            for (String key : List.of(prefix + e.code(), prefix + "product:" + e.hash())) {
                long id = catalogFixture(e.game(),e.code(),e.name(),key);
                boolean weiss = e.game().equals("WEISS");
                api.perform(get("/api/v1/packs/" + id).param("lang", "ja").param("size","1"))
                        .andExpect(status().isOk())
                        .andExpect(jsonPath("$.wikiProductReference.region").value("EN"))
                        .andExpect(jsonPath("$.wikiProductReference.productName").value(e.name()))
                        .andExpect(jsonPath("$.wikiProductReference.releaseDate").value(e.date()))
                        .andExpect(jsonPath("$.wikiProductReference.verificationUrl").value(e.url()))
                        .andExpect(jsonPath("$.wikiProductReference.title").value(weiss ? "바이스 슈발츠" : "리프트바운드"))
                        .andExpect(jsonPath("$.wikiProductReference.snapshotRow").value(weiss ? 1667755 : 266848))
                        .andExpect(jsonPath("$.wikiProductReference.snapshotDate").value("2026-08-29"));
            }
        }
        long relabeled = db.sql("update pack set name='Origins (다른 판본)' where legacy_key='catalog:RIFTBOUND:OGN' returning id")
                .query(Long.class).single();
        api.perform(get("/api/v1/packs/" + relabeled))
                .andExpect(jsonPath("$.wikiProductReference").doesNotHaveJsonPath());
        for (long id : List.of(
                catalogFixture("WEISS","SAO/S47","PR Card 【Schwarz Side】",
                        "catalog:WEISS:product:3177ac0f3b8c2440eabca84669bd0a08b61e526aa8df2c80e034a2ba72af7886"),
                catalogFixture("WEISS","SAO/S47","별도 일본어판","catalog:WEISS:test:ja"),
                catalogFixture("WEISS","SAO/S47","Sword Art Online Re: Edit","catalog:WEISS:other-edition"),
                catalogFixture("RIFTBOUND","OGN","Origins","manual:test-wiki-origins"))) {
            api.perform(get("/api/v1/packs/" + id)).andExpect(status().isOk())
                    .andExpect(jsonPath("$.wikiProductReference").doesNotHaveJsonPath());
        }
    }

    private long catalogFixture(String game,String code,String name,String key) {
        return db.sql("select id from pack where legacy_key=?").param(key).query(Long.class).optional()
                .orElseGet(() -> db.sql("insert into pack(game_code,code,name,legacy_key) values(?,?,?,?) returning id")
                        .param(game).param(code).param(name).param(key).query(Long.class).single());
    }

    @Test void allSixGamesExposeAllPagesAndOnlyDocumentedInclusionsAndRarities() throws Exception {
        for (String game : new String[]{"YUGIOH","POKEMON","WEISS","NIVEL","RIFTBOUND","ONEPIECE"}) {
            long pack = db.sql("insert into pack(game_code,name) values(?,'Pack coverage') returning id")
                    .param(game).query(Long.class).single();
            String url = "/api/v1/packs/"+pack;
            api.perform(get(url)).andExpect(status().isOk())
                    .andExpect(jsonPath("$.contentsStatus").value("NO_REGISTERED_CARDS"))
                    .andExpect(jsonPath("$.cards").isEmpty()).andExpect(jsonPath("$.rarityCounts").isEmpty());
            long first = db.sql("""
                    insert into card(game_code,pack_id,name,number,rarity,status,specs)
                    values(?,?,'A','P-10','Super Rare','PUBLISHED','{"names":{"en":"Alpha","ja":"十番"}}') returning id
                    """).param(game).param(pack).query(Long.class).single();
            db.sql("insert into card_variant(card_id,position,rarity) values(?,0,'Super Rare'),(?,1,'Parallel')")
                    .param(first).param(first).update();
            db.sql("""
                    insert into card(game_code,pack_id,name,number,status,specs)
                    values(?,?,'B','P-2','PUBLISHED','{"nw":"신규","names":{"en":"Beta","ja":"二番"}}'),
                          (?,?,'Draft','P-1','PENDING','{}')
                    """).param(game).param(pack).param(game).param(pack).update();
            for (String lang : new String[]{"en","ja","ko"}) {
                api.perform(get(url).param("page","0").param("size","1").param("sort","number").param("lang",lang))
                        .andExpect(status().isOk()).andExpect(jsonPath("$.total").value(2))
                        .andExpect(jsonPath("$.contentsStatus").value("REGISTERED"))
                        .andExpect(jsonPath("$.unknownInclusionCount").value(1)).andExpect(jsonPath("$.unknownRarityCount").value(1))
                        .andExpect(jsonPath("$.rarityCounts[0].rarity").value("Parallel"))
                        .andExpect(jsonPath("$.rarityCounts[1].rarity").value("Super Rare"))
                        .andExpect(jsonPath("$.rarityCounts[1].count").value(1))
                        .andExpect(jsonPath("$.hasMore").value(true)).andExpect(jsonPath("$.cards[0].number").value("P-2"))
                        .andExpect(jsonPath("$.cards[0].name").value(lang.equals("en")?"Beta":lang.equals("ja")?"二番":"B"));
                api.perform(get(url).param("page","1").param("size","1").param("sort","number").param("lang",lang))
                        .andExpect(status().isOk()).andExpect(jsonPath("$.hasMore").value(false))
                        .andExpect(jsonPath("$.cards[0].id").value(first));
            }
            for (String sort : new String[]{"source","name","rarity"}) {
                api.perform(get(url).param("size","1").param("sort",sort).param("lang","en"))
                        .andExpect(status().isOk()).andExpect(jsonPath("$.cards[0].id").value(first));
            }
            api.perform(get(url).param("page","2").param("size","1")).andExpect(status().isOk())
                    .andExpect(jsonPath("$.total").value(2)).andExpect(jsonPath("$.hasMore").value(false))
                    .andExpect(jsonPath("$.cards").isEmpty());
            api.perform(get(url).param("sort","price")).andExpect(status().isBadRequest());
        }
    }

    @Test void editedDateFollowsOnlyTheChosenPack() throws Exception {
        long selected = pack("Same product","catalog:date-test-picked","{}");
        long other = pack("Same product","catalog:date-test-other","{}");
        long event = db.sql("""
                insert into product_release(game_code,product_key,name,region,release_date,source_url,selected_pack_id,manual)
                values('YUGIOH','date-test','same date','KR','2027-01-22','https://example.test/date',?,true) returning id
                """).param(selected).query(Long.class).single();
        String url = "/api/v1/packs/";
        api.perform(get(url+selected)).andExpect(jsonPath("$.releaseDate").value("2027-01-22"));
        api.perform(get(url+other)).andExpect(jsonPath("$.releaseDate").isEmpty());
        db.sql("update product_release set release_date='2027-01-28' where id=?").param(event).update();
        api.perform(get(url+selected)).andExpect(jsonPath("$.releaseDate").value("2027-01-28"));
        db.sql("update product_release set selected_pack_id=null where id=?").param(event).update();
        api.perform(get(url+selected)).andExpect(jsonPath("$.releaseDate").isEmpty());
    }

    @Test void formerNivelPackLinksReachTheCorrectBoosterAndListsShowItOnce() throws Exception {
        long booster = db.sql("""
            insert into pack(game_code,code,name,legacy_key)
            values('NIVEL','SB02','Nivel product fixture','catalog:NIVEL:fixture-new') returning id
            """).query(Long.class).single();
        long old = db.sql("""
            insert into pack(game_code,code,name,legacy_key,superseded_by)
            values('NIVEL','ST08','Nivel product fixture','catalog:NIVEL:fixture-old',?) returning id
            """).param(booster).query(Long.class).single();
        long card = db.sql("""
            insert into card(game_code,pack_id,name,number,status,rarity)
            values('NIVEL',?,'타락의 유열 샬럿','ST08-014','PUBLISHED','SR') returning id
            """).param(booster).query(Long.class).single();
        db.sql("""
            insert into product_release(game_code,product_key,region,name,release_date,source_url,manual,selected_pack_id)
            values('NIVEL','fixture:old-pack','KR','Nivel product fixture','2026-01-25','https://example.invalid',true,?)
            """).param(old).update();
        api.perform(get("/api/v1/catalog-packs").param("game","NIVEL").param("q","Nivel product fixture"))
            .andExpect(status().isOk()).andExpect(jsonPath("$.total").value(1))
            .andExpect(jsonPath("$.items[0].id").value(booster));
        api.perform(get("/api/v1/packs/"+old)).andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(booster)).andExpect(jsonPath("$.code").value("SB02"))
            .andExpect(jsonPath("$.cards[0].id").value(card)).andExpect(jsonPath("$.rarityCounts[0].count").value(1));
        api.perform(get("/api/v1/cards").param("packId",""+old)).andExpect(status().isOk())
            .andExpect(jsonPath("$.items[0].id").value(card));
        api.perform(get("/api/v1/release-calendar").param("packId",""+old).param("period","all"))
            .andExpect(status().isOk()).andExpect(jsonPath("$.items[0].catalogPackId").value(booster))
            .andExpect(jsonPath("$.items[0].catalogCount").value(1));
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
