package kr.tcghub;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.transaction.annotation.Transactional;
import java.nio.file.Files;
import java.nio.file.Path;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
@EnabledIfEnvironmentVariable(named="TCG_TEST_DB",matches="1")
@Transactional
class CatalogBrowseIntegrationTest {
    @Autowired JdbcClient db;
    @Autowired MockMvc http;

    @Test void koreanFirstOrderSpansPagesAndReflectsNewlyCachedFiles() throws Exception {
        long pack=db.sql("insert into pack(game_code,name) values('POKEMON','Browse ordering') returning id").query(Long.class).single();
        String insert="insert into card(pack_id,game_code,name,specs,status) values(?,'POKEMON',?,cast(? as jsonb),'PUBLISHED') returning id";
        long unknown=db.sql(insert).param(pack).param("Unnamed").param("{}").query(Long.class).single();
        long japanese=db.sql(insert).param(pack).param("JP").param("{\"language\":\"ja\",\"images\":{\"ja\":\"https://example.org/browse-jp\"}}").query(Long.class).single();
        long label=db.sql(insert).param(pack).param("한국어 이름").param("{\"language\":\"ko\"}").query(Long.class).single();
        long korean=db.sql(insert).param(pack).param("Korean art").param("{\"images\":{\"ko\":\"https://example.org/browse-ko\"}}").query(Long.class).single();
        CachedArtwork.link(db,japanese,"https://example.org/browse-jp",'4');
        CachedArtwork.link(db,korean,"https://example.org/browse-ko",'5');
        long[] expected={korean,label,japanese,unknown};
        for (int i=0;i<expected.length;i++)
            http.perform(get("/api/v1/cards").param("packId",""+pack).param("order","edition").param("page",""+i).param("size","1"))
                    .andExpect(status().isOk()).andExpect(jsonPath("$.total").value(4)).andExpect(jsonPath("$.items[0].id").value(expected[i]));
        db.sql("update catalog_art_file set storage_key=null where source_url=?").param("https://example.org/browse-ko").update();
        http.perform(get("/api/v1/cards").param("packId",""+pack).param("order","edition").param("withImage","true"))
                .andExpect(jsonPath("$.total").value(1)).andExpect(jsonPath("$.items[0].id").value(japanese));
    }

    @Test void upgradingNivelArtworkKeepsExistingThumbnailUntilTheFullFileArrives() throws Exception {
        String small="http://nivelarena.co.kr/data/file/cardlists/thumb-card.png";
        String full="http://nivelarena.co.kr/data/file/cardlists/card.png";
        long card=db.sql("""
                insert into card(game_code,name,specs,status) values('NIVEL','니벨 조회',
                jsonb_build_object('images',jsonb_build_object('ko',cast(? as text))),'PUBLISHED') returning id
                """).param(small).query(Long.class).single();
        String oldPath=CachedArtwork.link(db,card,small,'8');
        db.sql("""
                update card set specs=specs||jsonb_build_object('images',jsonb_build_object('ko',cast(? as text)),
                'nivelThumbnail',cast(? as text)) where id=?
                """).param(full).param(small).param(card).update();
        http.perform(get("/api/v1/cards/"+card)).andExpect(jsonPath("$.imageUrl").value(oldPath))
                .andExpect(jsonPath("$.specs.images.ko").value(oldPath)).andExpect(jsonPath("$.specs.nivelThumbnail").doesNotExist());
        assertEquals(2,db.sql("select mask from catalog_browse_photo where card_id=?").param(card).query(Integer.class).single());
        String newPath=CachedArtwork.link(db,card,full,'9');
        http.perform(get("/api/v1/cards/"+card)).andExpect(jsonPath("$.imageUrl").value(newPath))
                .andExpect(jsonPath("$.specs.images.ko").value(newPath));
        db.sql("update card set specs=specs-'nivelThumbnail' where id=?").param(card).update();
        assertEquals(1,db.sql("select count(*) from catalog_art_card where card_id=?").param(card).query(Integer.class).single());
    }

    @Test void koreanFirstIncludesLinkedAndSupplementalNamesAndFollowsWithdrawal() throws Exception {
        long pack=db.sql("insert into pack(game_code,name) values('YUGIOH','External names') returning id").query(Long.class).single();
        String insert="insert into card(pack_id,game_code,number,name,original_name,status) values(?,'YUGIOH',?,?,'JP','PUBLISHED') returning id";
        long unknown=db.sql(insert).param(pack).param("EXT001").param("Unregistered").query(Long.class).single();
        long known=db.sql(insert).param(pack).param("EXT002").param("JP").query(Long.class).single();
        db.sql("""
                insert into legacy_card_edition(card_id,matched_number,matched_name,names,texts,source_url)
                values(?,'EXT002','JP','{"ko":"길 거스"}','{}','https://example.org/edition')
                """).param(known).update();
        assertRankedFirst(pack,known);
        db.sql("update legacy_card_edition set matched_number='other' where card_id=?").param(known).update();
        assertRankedFirst(pack,unknown);
        db.sql("""
                insert into supplemental_printing(provider,game_code,external_id,card_id,number,name,lang,source_url)
                values('fixture','YUGIOH','EXT002',?,'EXT002','길 거스','ko','https://example.org/name')
                """).param(known).update();
        assertRankedFirst(pack,known);
        db.sql("delete from supplemental_printing where card_id=?").param(known).update();
        assertRankedFirst(pack,unknown);
        db.sql("""
                update card set legacy_key='catalog:YUGIOH:known-title', specs='{"konami_id":9998765,"passcode":"12345"}' where id=?
                """).param(known).update();
        db.sql("""
                insert into wiki_card_document(game_code,lookup_key,passcode,title,document_url,snapshot_date,snapshot_url,
                    verification_url,names,facts) values('YUGIOH','cid:9998765','12345','검증','https://namu.wiki/w/검증',
                    '2021-03-01','https://example.org/snapshot','https://example.org/print','{"ko":"길 거스"}','{}')
                """).update();
        assertRankedFirst(pack,known);
        db.sql("update wiki_card_document set passcode='54321' where lookup_key='cid:9998765'").update();
        assertRankedFirst(pack,unknown);
    }

    private void assertRankedFirst(long pack,long expected) throws Exception {
        http.perform(get("/api/v1/cards").param("packId",""+pack).param("order","edition").param("size","1"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.items[0].id").value(expected));
    }

    @Test void aConditionalImageRequestStillChecksCurrentVisibility(@TempDir Path media) throws Exception {
        long card=db.sql("insert into card(game_code,name,status) values('NIVEL','미리보기','PUBLISHED') returning id")
                .query(Long.class).single();
        String path=CachedArtwork.link(db,card,"https://example.org/conditional",'7');
        Path file=media.resolve(path.substring("/media/".length()));
        Files.createDirectories(file.getParent());
        Files.write(file,new byte[]{1,2,3});
        var server=MockMvcBuilders.standaloneSetup(new WebRoutes(media.toString(),db)).build();
        var response=server.perform(get(path)).andExpect(status().isOk()).andExpect(header().string("Cache-Control","no-cache"))
                .andReturn().getResponse();
        String tag=response.getHeader("ETag");
        server.perform(get(path).header("If-None-Match",tag)).andExpect(status().isNotModified());
        db.sql("update card set status='PENDING' where id=?").param(card).update();
        server.perform(get(path).header("If-None-Match",tag)).andExpect(status().isNotFound());
    }

    @Test void pendingTileDoesNotLeaveAnUnservableThumbnailOnAnotherPublicCard() throws Exception {
        String insert="insert into card(game_code,name,status) values('WEISS','Atlas test',?) returning id";
        long ready=db.sql(insert).param("PUBLISHED").query(Long.class).single();
        long pending=db.sql(insert).param("PENDING").query(Long.class).single();
        long sheet=db.sql("insert into image_sheet(storage_key,cell_width,cell_height) values('sheets/mixed-test.webp',20,30) returning id").query(Long.class).single();
        db.sql("insert into card_variant(card_id,sheet_id,col_idx,row_idx) values(?,?,0,0),(?,?,1,0)")
                .param(ready).param(sheet).param(pending).param(sheet).update();
        http.perform(get("/api/v1/cards").param("ids",""+ready).param("withImage","true")).andExpect(jsonPath("$.total").value(0));
        assertEquals(0,db.sql("select count(*) from catalog_browse_photo where card_id=?").param(ready).query(Integer.class).single());
        db.sql("update card set status='PUBLISHED' where id=?").param(pending).update();
        // Republishing queues the old atlas for repacking. It is visible again on the replacement sheet.
        long repacked=db.sql("insert into image_sheet(storage_key,cell_width,cell_height) values('sheets/repacked.webp',20,30) returning id").query(Long.class).single();
        db.sql("update card_variant set sheet_id=? where sheet_id=?").param(repacked).param(sheet).update();
        http.perform(get("/api/v1/cards").param("ids",""+ready).param("withImage","true")).andExpect(jsonPath("$.total").value(1));
    }
}
