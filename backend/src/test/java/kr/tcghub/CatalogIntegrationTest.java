package kr.tcghub;

import java.util.UUID;
import java.nio.file.Files;
import java.nio.file.Path;
import jakarta.servlet.http.Cookie;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;
import org.springframework.transaction.annotation.Transactional;
import com.fasterxml.jackson.databind.ObjectMapper;
import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

/** Run against a dedicated PostGIS test database using the normal deployment environment. */
@SpringBootTest
@AutoConfigureMockMvc
@EnabledIfEnvironmentVariable(named="TCG_TEST_DB",matches="1")
@Transactional
class CatalogIntegrationTest {
    @Autowired MockMvc api;
    @Autowired JdbcClient db;
    @Autowired ObjectMapper json;
    @Value("${tcg.public-origin}") String origin;

    @Test void practiceLabelsMatchThePrintingAndReportLanguageFallback() throws Exception {
        String name = "연습-" + UUID.randomUUID();
        long id = db.sql("""
                insert into card(game_code,name,specs,status) values('POKEMON',?,
                    '{"language":"ko","names":{"ja":"練習用"}}'::jsonb,'PUBLISHED') returning id
                """).param(name).query(Long.class).single();
        long hidden = db.sql("insert into card(game_code,name) values('POKEMON',?) returning id")
                .param(name).query(Long.class).single();
        api.perform(get("/api/v1/play/cards").param("game","POKEMON").param("lang","ja")
                        .param("ids",id+","+hidden))
                .andExpect(status().isOk()).andExpect(jsonPath("$.length()").value(1))
                .andExpect(jsonPath("$[0].name").value("練習用")).andExpect(jsonPath("$[0].language").value("ja"));
        api.perform(get("/api/v1/play/cards").param("game","POKEMON").param("lang","en").param("q",name))
                .andExpect(status().isOk()).andExpect(jsonPath("$[0].name").value(name))
                .andExpect(jsonPath("$[0].language").value("ko"));
        api.perform(get("/api/v1/play/cards").param("game","YUGIOH").param("ids",String.valueOf(id)))
                .andExpect(status().isOk()).andExpect(jsonPath("$.length()").value(0));
        api.perform(get("/api/v1/play/cards").param("game","POKEMON").param("lang","fr")).andExpect(status().isBadRequest());
    }

    @Test void atlasLocaleFollowsTheDisplayedPixelsAcrossCatalogAndPlay() throws Exception {
        String name = "atlas-" + UUID.randomUUID();
        long id = db.sql("insert into card(game_code,name,status) values('YUGIOH',?,'PUBLISHED') returning id")
                .param(name).query(Long.class).single();
        String key = "sheets/" + "e".repeat(64) + ".webp";
        long sheet = db.sql("insert into image_sheet(storage_key,cell_width,cell_height) values(?,200,290) returning id")
                .param(key).query(Long.class).single();
        db.sql("insert into verified_atlas_edition values (?,0,0,'en'),(?,1,0,'ja')").param(key).param(key).update();
        db.sql("insert into card_variant(card_id,position,sheet_id,col_idx,row_idx) values (?,0,?,0,0),(?,1,?,1,0)")
                .param(id).param(sheet).param(id).param(sheet).update();
        for (String lang : java.util.List.of("ja","ko","en")) {
            boolean japanese = lang.equals("ja");
            String expected = japanese ? "ja" : "en";
            api.perform(get("/api/v1/cards").param("q",name).param("lang",lang))
                    .andExpect(status().isOk()).andExpect(jsonPath("$.items[0].image.language").value(expected))
                    .andExpect(jsonPath("$.items[0].image.col").value(japanese ? 1 : 0));
            api.perform(get("/api/v1/play/cards").param("game","YUGIOH").param("ids",String.valueOf(id)).param("lang",lang))
                    .andExpect(status().isOk()).andExpect(jsonPath("$[0].image.language").value(expected))
                    .andExpect(jsonPath("$[0].image.col").value(japanese ? 1 : 0));
        }
        api.perform(get("/api/v1/cards/"+id).param("lang","ja")).andExpect(status().isOk())
                .andExpect(jsonPath("$.variants[0].image.language").value("en"))
                .andExpect(jsonPath("$.variants[1].image.language").value("ja"))
                .andExpect(jsonPath("$.imageLanguage").isEmpty());
        long replacement = db.sql("insert into image_sheet(storage_key,cell_width,cell_height) values(?,200,290) returning id")
                .param("sheets/" + "f".repeat(64) + ".webp").query(Long.class).single();
        db.sql("update card_variant set sheet_id=? where card_id=? and position=0").param(replacement).param(id).update();
        api.perform(get("/api/v1/cards/"+id)).andExpect(status().isOk())
                .andExpect(jsonPath("$.variants[0].image.sheetId").value(replacement))
                .andExpect(jsonPath("$.variants[0].image.language").isEmpty())
                .andExpect(jsonPath("$.variants[1].image").isEmpty());
    }

    @Test void onlyPublishedCardsAndCorrectTileReachTheCatalog() throws Exception {
        String keyword = "검증-" + UUID.randomUUID();
        long card = db.sql("insert into card(game_code,name,status) values('NIVEL',?,'PUBLISHED') returning id")
                .param(keyword).query(Long.class).single();
        long hidden = db.sql("insert into card(game_code,name) values('NIVEL',?) returning id")
                .param(keyword).query(Long.class).single();
        long sheet = db.sql("insert into image_sheet(storage_key,cell_width,cell_height) values(?,300,438) returning id")
                .param("sheets/" + UUID.randomUUID() + ".webp").query(Long.class).single();
        db.sql("insert into card_variant(card_id,rarity,sheet_id,col_idx,row_idx) values(?,'R SR',?,3,2)")
                .param(card).param(sheet).update();
        api.perform(get("/api/v1/cards").param("game","NIVEL").param("q",keyword).param("rarity","SR"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.total").value(1))
                .andExpect(jsonPath("$.items[0].name").value(keyword))
                .andExpect(jsonPath("$.items[0].image.sheetId").value(sheet)).andExpect(jsonPath("$.items[0].image.row").value(2));
        api.perform(get("/api/v1/cards/" + card)).andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value(keyword)).andExpect(jsonPath("$.variants[0].image.col").value(3))
                .andExpect(jsonPath("$.variants[0].image.row").value(2));
        api.perform(get("/api/v1/cards/" + hidden)).andExpect(status().isNotFound());
        db.sql("update card_variant set rarity='Super Rare' where card_id=?").param(card).update();
        db.sql("update image_sheet set retired=true where id=?").param(sheet).update();
        api.perform(get("/api/v1/cards").param("q",keyword).param("rarity","super rare"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.total").value(1)).andExpect(jsonPath("$.items[0].image").isEmpty());
        api.perform(get("/api/v1/cards").param("size","101")).andExpect(status().isBadRequest());
    }

    private MockHttpServletRequestBuilder write(String action) {
        String path = "/api/v1/auth/" + action;
        return post(path).servletPath(path).header("Origin",origin).header("X-TCG-Request","1");
    }

    @Test void onlySheetsLinkedToPublishedCardsCanBeServed(@TempDir Path root) throws Exception {
        var media = new WebRoutes(root.toString(), db);
        String filename = UUID.randomUUID().toString().replace("-","").repeat(2) + ".webp";
        Files.createDirectory(root.resolve("sheets"));
        Files.createFile(root.resolve("sheets").resolve(filename));
        long sheet = db.sql("insert into image_sheet(storage_key,cell_width,cell_height) values(?,300,438) returning id")
                .param("sheets/" + filename).query(Long.class).single();
        long card = db.sql("insert into card(game_code,name,status) values('NIVEL','미디어 검사','PUBLISHED') returning id")
                .query(Long.class).single();
        db.sql("insert into card_variant(card_id,sheet_id,col_idx,row_idx) values(?,?,0,0)")
                .param(card).param(sheet).update();
        assertEquals(200, media.media("sheets",filename).getStatusCode().value());
        db.sql("update card set status='PENDING' where id=?").param(card).update();
        var hidden = assertThrows(org.springframework.web.server.ResponseStatusException.class,
                () -> media.media("sheets",filename));
        assertEquals(404,hidden.getStatusCode().value());
        db.sql("update card set status='PUBLISHED' where id=?").param(card).update();
        assertThrows(org.springframework.web.server.ResponseStatusException.class, () -> media.media("sheets",filename));
    }

    @Test void rotationLogoutAndAdminBoundary() throws Exception {
        String email = UUID.randomUUID() + "@example.invalid";
        String password = UUID.randomUUID().toString();
        db.sql("insert into app_user(email,password_hash) values(?,?)")
                .param(email).param(new BCryptPasswordEncoder().encode(password)).update();
        var login = api.perform(write("login").contentType(MediaType.APPLICATION_JSON)
                .content(json.writeValueAsString(new Accounts.Login(email,password))))
                .andExpect(status().isOk()).andExpect(header().string("Cache-Control",org.hamcrest.Matchers.containsString("no-store")))
                .andExpect(jsonPath("$.role").value("ROLE_USER")).andReturn().getResponse();
        var original = login.getCookie("__Secure-tcg_refresh");
        assertNotNull(original);
        assertTrue(original.isHttpOnly() && original.getSecure());
        assertTrue(login.getHeader("Set-Cookie").contains("SameSite=Strict"));
        String access = json.readTree(login.getContentAsString()).get("accessToken").textValue();
        api.perform(get("/api/v1/admin/status").header("Authorization","Bearer " + access)).andExpect(status().isForbidden());
        String refreshPath = "/api/v1/auth/refresh";
        api.perform(post(refreshPath).servletPath(refreshPath).cookie(original).header("Origin",origin))
                .andExpect(status().isForbidden());
        api.perform(post(refreshPath).servletPath(refreshPath).cookie(original)
                .header("Origin","https://other.invalid").header("X-TCG-Request","1")).andExpect(status().isForbidden());
        Cookie rotated = api.perform(write("refresh").cookie(original)).andExpect(status().isOk())
                .andReturn().getResponse().getCookie("__Secure-tcg_refresh");
        assertNotNull(rotated);
        assertNotEquals(original.getValue(),rotated.getValue());
        api.perform(write("refresh").cookie(original)).andExpect(status().isUnauthorized());
        api.perform(write("logout").cookie(rotated)).andExpect(status().isNoContent());
        api.perform(write("refresh").cookie(rotated)).andExpect(status().isUnauthorized());
    }
}
