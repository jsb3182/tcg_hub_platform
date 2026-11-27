package kr.tcghub;

import java.awt.image.BufferedImage;
import java.io.ByteArrayOutputStream;
import java.time.LocalDate;
import java.util.*;
import javax.imageio.ImageIO;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;
import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest @Transactional
@EnabledIfEnvironmentVariable(named="TCG_TEST_DB",matches="1")
class ReleaseAndCaptureIntegrationTest {
    @Autowired JdbcClient db;
    @Autowired DeckCaptureMatcher matcher;
    @Autowired AdminReleaseApi admin;
    @Autowired ReleaseCalendarApi calendar;
    @Autowired CatalogApi catalog;
    @Autowired DeckApi decks;

    @Test void operatorChangeUsesTheCurrentVersionAndPublicCalendarFilters() throws Exception {
        String email=UUID.randomUUID()+"@example.invalid";
        db.sql("insert into app_user(email,password_hash,role) values(?,'unused','ROLE_ADMIN')").param(email).update();
        var day=LocalDate.of(2087,3,10);
        var input=new AdminReleaseApi.Input("WEISS","KR","QA","부스터 검증",Map.of("ko","부스터 검증"),
                day,"https://ws-tcg.com/",null,"BOOSTER",null);
        var result=admin.create(input,()->email);
        long id=((Number)result.get("id")).longValue();
        long version=((Number)admin.get(id).get("version")).longValue();
        var updated=new AdminReleaseApi.Input("WEISS","KR","QA","특별판 검증",Map.of("ko","특별판 검증"),
                day.plusDays(2),input.sourceUrl(),null,"SPECIAL",version);
        admin.update(id,updated,()->email);
        assertEquals(1,calendar.list("WEISS,POKEMON","KR,JP","SPECIAL","2087-03","all","특별판 검증",null,0,10).total());
        assertEquals(0,calendar.list("WEISS","KR","BOOSTER","2087-03","all","특별판 검증",null,0,10).total());
        assertEquals(409,assertThrows(ResponseStatusException.class,()->admin.update(id,updated,()->email)).getStatusCode().value());
    }

    @Test void gridCaptureRestrictsMatchesToTheGameAndMarksBlankSlots() throws Exception {
        var image=new BufferedImage(104,80,BufferedImage.TYPE_INT_RGB);
        for (int x=0;x<52;x++) for (int y=0;y<80;y++) {
            int shade=((x/4+y/9)%2)*255;
            image.setRGB(x,y,shade*0x010101);
        }
        long cid=db.sql("insert into card(game_code,name,number,status) values('WEISS','배열 검수','QA-10','PUBLISHED') returning id").query(Long.class).single();
        var url="https://en.ws-tcg.com/test/"+UUID.randomUUID()+".png";
        CachedArtwork.link(db,cid,url,'a');
        String bits=Long.toBinaryString(DeckCaptureMatcher.signature(image,0,0,52,80));
        db.sql("update catalog_art_file set capture_hash=cast(? as bit(64)) where source_url=?")
                .params("0".repeat(64-bits.length())+bits,url).update();
        var bytes=new ByteArrayOutputStream();
        ImageIO.write(image,"png",bytes);
        var upload=new MockMultipartFile("file","deck.png","image/png",bytes.toByteArray());
        var result=matcher.match(upload,"WEISS",2,1,0,0,1,1);
        assertEquals(cid,result.slots().get(0).candidates().get(0).cardId());
        assertEquals(1d,result.slots().get(0).candidates().get(0).confidence());
        assertTrue(result.slots().get(1).candidates().isEmpty());
        assertTrue(result.slots().get(1).needsReview());
        assertTrue(matcher.match(upload,"NIVEL",2,1,0,0,1,1).slots().stream()
                .flatMap(s->s.candidates().stream()).noneMatch(c->c.cardId()==cid));
        assertThrows(ResponseStatusException.class,()->matcher.match(upload,"WEISS",2,1,0,0,.02,1));
    }

    @Test void privateDeckStockAndActualPriceSurviveFilteringWithoutLeakingToSharedDecks() throws Exception {
        var actor=(java.security.Principal)()->"deck-qa@example.invalid";
        long owner=db.sql("insert into app_user(email,password_hash) values(?,'x') returning id").param(actor.getName()).query(Long.class).single();
        long card=db.sql("insert into card(game_code,name,rarity,status) values('WEISS','수록 검증','RR','PUBLISHED') returning id").query(Long.class).single();
        long variant=db.sql("insert into card_variant(card_id,position,rarity) values(?,0,'RR') returning id").param(card).query(Long.class).single();
        long listing=db.sql("insert into price_listing(variant_id,provider,external_key) values(?,'QA','edition') returning id").param(variant).query(Long.class).single();
        db.sql("insert into price_snapshot(listing_id,observed_at,currency,amount) values(?,'2020-01-01','KRW',2000),(?,now(),'KRW',3000)")
                .params(listing,listing).update();
        assertEquals(3000,catalog.details(card,"ko").prices().get(0).amount().intValueExact());
        db.sql("insert into binder_card(owner_id,card_id,quantity) values(?,?,2)").params(owner,card).update();
        decks.create(actor,new DeckApi.Save("다른 종목","POKEMON","DRAFT",0,false,List.of()));
        var saved=decks.create(actor,new DeckApi.Save("내 바이스","WEISS","DRAFT",0,true,List.of(new DeckRules.Line(card,"MAIN",1))));
        var filtered=decks.list(actor,0,"바이스","WEISS");
        assertEquals(2,filtered.allTotal()); assertEquals(1,filtered.total());
        assertEquals(2,filtered.items().get(0).ordinal()); assertEquals(1L,filtered.items().get(0).sectionCounts().get("MAIN"));
        assertEquals(2L,saved.entries().get(0).ownedCopies());
        assertNull(decks.shared(saved.deck().shareToken(),"ko").entries().get(0).ownedCopies());
    }
}
