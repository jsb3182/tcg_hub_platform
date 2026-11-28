package kr.tcghub;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.annotation.Transactional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
@EnabledIfEnvironmentVariable(named="TCG_TEST_DB",matches="1")
@Transactional
class RegionalArtworkIntegrationTest {
    @Autowired JdbcClient db;
    @Autowired MockMvc http;

    @Test void sourceRefreshRetainsOnlyPreviouslyGrantedUnchangedEditions(@TempDir java.nio.file.Path media) throws Exception {
        long id=db.sql("""
            insert into card(game_code,name,number,specs,status) values ('RIFTBOUND','Art refresh','OGN-100',
                  '{"language":"en","images":{"en":"https://example.org/en"}}','PUBLISHED') returning id
            """).query(Long.class).single();
        String english=CachedArtwork.link(db,id,"https://example.org/en",'5');
        WebRoutes publicFiles=new WebRoutes(media.toString(),db);
        String filename=java.nio.file.Path.of(english).getFileName().toString();
        java.nio.file.Files.createDirectories(media.resolve("cards"));
        java.nio.file.Files.write(media.resolve("cards").resolve(filename),
                java.util.Base64.getDecoder().decode("UklGRhwAAABXRUJQVlA4TA8AAAAvAAAAAAcQUcD+ByKi/wEA"));
        db.sql("update card set specs=jsonb_set(specs,'{images,ko}',to_jsonb(cast(? as text))) where id=?")
                .param("https://example.org/ko").param(id).update();
        http.perform(get("/api/v1/cards/"+id).param("lang","ja")).andExpect(jsonPath("$.imageUrl").value(english))
                .andExpect(jsonPath("$.imageLanguage").value("en"));
        assertEquals(200,publicFiles.media("cards",filename).getStatusCode().value());
        CachedArtwork.link(db,id,"https://example.org/ko",'6');
        db.sql("""
                update card set specs=jsonb_set(specs,'{images}',cast(? as jsonb)) where id=?
                """).param("{\"en\":\"https://example.org/new\",\"ja\":\"https://example.org/ko\"}").param(id).update();
        assertEquals(0L,db.sql("select count(*) from catalog_art_card where card_id=?").param(id).query(Long.class).single());
        assertEquals(404,assertThrows(org.springframework.web.server.ResponseStatusException.class,
                () -> publicFiles.media("cards",filename)).getStatusCode().value());
        http.perform(get("/api/v1/cards/"+id)).andExpect(jsonPath("$.imageUrl").isEmpty());
        CachedArtwork.link(db,id,"https://example.org/new",'7');
        db.sql("update card set number='OGN-200' where id=?").param(id).update();
        assertEquals(0L,db.sql("select count(*) from catalog_art_card where card_id=?").param(id).query(Long.class).single());
        CachedArtwork.link(db,id,"https://example.org/new",'7');
        db.sql("update card set status='PENDING' where id=?").param(id).update();
        assertEquals(0L,db.sql("select count(*) from catalog_art_card where card_id=?").param(id).query(Long.class).single());
        http.perform(get("/api/v1/cards/"+id)).andExpect(status().isNotFound());
    }

    @ParameterizedTest
    @ValueSource(strings={"YUGIOH","POKEMON","WEISS","NIVEL","RIFTBOUND","ONEPIECE"})
    void imageFilterUsesDisplayableEditionOrActiveAtlasBeforePaging(String game) throws Exception {
        long pack=db.sql("insert into pack(game_code,name) values(?,'Picture filter test') returning id")
                .param(game).query(Long.class).single();
        String data="""
            {"language":"en","images":{"ko":"https://example.org/kr","en":"https://example.org/en","ja":"https://example.org/jp"},
             "imageProducts":{"ja":"JP-SET"},"imageSources":{"ja":"https://example.org/jp/list"}}
            """;
        String insert="insert into card(game_code,pack_id,name,status,specs) values(?,?,'Picture test',?,cast(? as jsonb)) returning id";
        long empty=db.sql(insert).param(game).param(pack).param("PUBLISHED").param(data).query(Long.class).single();
        long direct=db.sql(insert).param(game).param(pack).param("PUBLISHED").param(data).query(Long.class).single();
        long atlas=db.sql(insert).param(game).param(pack).param("PUBLISHED").param("{}").query(Long.class).single();
        long hidden=db.sql(insert).param(game).param(pack).param("PENDING").param(data).query(Long.class).single();
        long retired=db.sql(insert).param(game).param(pack).param("PUBLISHED").param("{}").query(Long.class).single();
        String jp=CachedArtwork.link(db,direct,"https://example.org/jp",'8');
        CachedArtwork.link(db,hidden,"https://example.org/jp",'8');
        CachedArtwork.link(db,empty,"https://example.org/old-replaced-edition",'9');
        long sheet=db.sql("insert into image_sheet(storage_key,cell_width,cell_height) values('sheets/image-filter.webp',20,30) returning id")
                .query(Long.class).single();
        long oldSheet=db.sql("insert into image_sheet(storage_key,cell_width,cell_height,retired) values('sheets/older-image-filter.webp',20,30,true) returning id")
                .query(Long.class).single();
        db.sql("insert into card_variant(card_id,sheet_id,col_idx,row_idx) values(?,?,0,1),(?,?,0,2)")
                .param(atlas).param(sheet).param(retired).param(oldSheet).update();
        for (String language : java.util.List.of("ko","en","ja"))
            http.perform(get("/api/v1/cards").param("packId",""+pack).param("game",game).param("lang",language)
                      .param("withImage","true").param("size","1")).andExpect(status().isOk())
                    .andExpect(jsonPath("$.total").value(2)).andExpect(jsonPath("$.items[0].id").value(direct))
                    .andExpect(jsonPath("$.items[0].imageUrl").value(jp)).andExpect(jsonPath("$.items[0].imageLanguage").value("ja"))
                    .andExpect(jsonPath("$.items[0].imageProduct").value("JP-SET"))
                    .andExpect(jsonPath("$.items[0].imageSource").value("https://example.org/jp/list"));
        http.perform(get("/api/v1/cards").param("packId",""+pack).param("withImage","true").param("size","1").param("page","1"))
                .andExpect(jsonPath("$.total").value(2)).andExpect(jsonPath("$.items[0].id").value(atlas))
                .andExpect(jsonPath("$.items[0].image.sheetId").value(sheet));
        http.perform(get("/api/v1/cards").param("packId",""+pack)).andExpect(jsonPath("$.total").value(4));
        http.perform(get("/api/v1/cards").param("ids",empty+","+atlas+","+hidden).param("withImage","true"))
                .andExpect(jsonPath("$.total").value(1)).andExpect(jsonPath("$.items[0].id").value(atlas));
        String en=CachedArtwork.link(db,direct,"https://example.org/en",'7');
        http.perform(get("/api/v1/cards/"+direct).param("lang","ko")).andExpect(jsonPath("$.imageUrl").value(en))
                .andExpect(jsonPath("$.imageLanguage").value("en"));
        String ko=CachedArtwork.link(db,direct,"https://example.org/kr",'6');
        http.perform(get("/api/v1/packs/"+pack).param("lang","ko")).andExpect(jsonPath("$.cards[1].imageUrl").value(ko));
    }

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
                .andExpect(jsonPath("$.imageUrl").isEmpty()).andExpect(jsonPath("$.specs.images.en").doesNotExist());
        String cachedKo=CachedArtwork.link(db,card,kr,'1');
        String cachedJa=CachedArtwork.link(db,card,"https://artworks-jp-n.ygoresources.com/0/40/41_1.png",'2');
        String cachedEn=CachedArtwork.link(db,card,"https://example.org/exact.png",'3');
        http.perform(get("/api/v1/cards/"+card).param("lang","ko")).andExpect(status().isOk())
                .andExpect(jsonPath("$.imageBasis").value("CARD_REFERENCE")).andExpect(jsonPath("$.imageLanguage").value("ko"))
                .andExpect(jsonPath("$.imageUrl").value(cachedKo)).andExpect(jsonPath("$.imageSource").value(kr))
                .andExpect(jsonPath("$.specs.images.en").value(cachedEn))
                .andExpect(jsonPath("$.imageProduct").isEmpty());
        http.perform(get("/api/v1/packs/"+pack).param("lang","ja")).andExpect(status().isOk())
                .andExpect(jsonPath("$.cards[0].imageUrl").value(cachedJa))
                .andExpect(jsonPath("$.cards[0].imageBasis").value("CARD_REFERENCE"));
        http.perform(get("/api/v1/play/cards").param("game","YUGIOH").param("ids",Long.toString(card)).param("lang","en"))
                .andExpect(jsonPath("$[0].imageUrl").value(cachedEn))
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
        String jp=db.sql("select ja_path from yugioh_reference_art where cid=?").param(cid).query(String.class).single();
        CachedArtwork.link(db,id,"https://artworks-jp-n.ygoresources.com"+jp,'4');
        http.perform(get("/api/v1/cards/"+id).param("lang","ko")).andExpect(status().isOk())
                .andExpect(jsonPath("$.imageLanguage").value("ja")).andExpect(jsonPath("$.imageBasis").value("CARD_REFERENCE"));
        db.sql("update card set game_code='POKEMON' where id=?").param(id).update();
        http.perform(get("/api/v1/cards/"+id).param("lang","ko")).andExpect(jsonPath("$.imageUrl").isEmpty());
    }
}
