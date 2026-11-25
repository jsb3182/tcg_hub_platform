package kr.tcghub;

import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.annotation.Transactional;
import static org.junit.jupiter.api.Assertions.*;
import static org.hamcrest.Matchers.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
@Transactional
@EnabledIfEnvironmentVariable(named="TCG_TEST_DB", matches="1")
class StoreApiIntegrationTest {
    @Autowired MockMvc http;
    @Autowired JdbcClient db;
    @Autowired Tokens tokens;
    @Value("${tcg.public-origin}") String origin;
    static final String SEARCH="/api/v1/stores";
    static final String FAVORITES="/api/v1/me/favorites/stores";

    @Test void seedHasAttributableKoreanLocationsAndIndexedRadiusResults() throws Exception {
        var point=db.sql("SELECT ST_X(location::geometry),ST_Y(location::geometry) FROM store WHERE semas_id='MA0101202608A0104832'")
                .query((rs,n) -> new double[]{rs.getDouble(1),rs.getDouble(2)}).single();
        http.perform(get(SEARCH).param("lat",Double.toString(point[1])).param("lon",Double.toString(point[0]))
                        .param("radiusKm","0.01").param("game","POKEMON"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.total").value(1))
                .andExpect(jsonPath("$.items[0].name").value("카드웨이브강릉"))
                .andExpect(jsonPath("$.items[0].distanceKm").value(0))
                .andExpect(jsonPath("$.items[0].sourceDate").value("2026-09-30"))
                .andExpect(jsonPath("$.items[0].hours.text").value(containsString("월 휴무")))
                .andExpect(jsonPath("$.items[0].games[0].source").value(containsString("pokemonkorea.co.kr")));
        http.perform(get(SEARCH).param("q","솔올로").param("game","RIFTBOUND"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.total").value(0));
        db.sql("SET LOCAL enable_seqscan=off").update();
        var plan=db.sql("EXPLAIN SELECT id FROM store WHERE ST_DWithin(location, ST_SetSRID(ST_MakePoint(127,37),4326)::geography,1000)")
                .query(String.class).list();
        assertTrue(plan.stream().anyMatch(line->line.contains("store_location_gist")));
    }

    @Test void missingAndInvalidCoordinatesAreRejected() throws Exception {
        http.perform(get(SEARCH).param("lat","37")).andExpect(status().isBadRequest());
        http.perform(get(SEARCH).param("radiusKm","10")).andExpect(status().isBadRequest());
        http.perform(get(SEARCH).param("lat","NaN").param("lon","127")).andExpect(status().isBadRequest());
        http.perform(get(SEARCH).param("lat","37").param("lon","127").param("radiusKm","501"))
                .andExpect(status().isBadRequest());
        http.perform(get(SEARCH).param("q","%'")).andExpect(status().isOk()).andExpect(jsonPath("$.total").value(0));
    }

    @Test void favoritesRequireAnEnabledAccountAndStayPrivateAndIdempotent() throws Exception {
        long id=db.sql("SELECT id FROM store WHERE semas_id='MA0101202608A0104832'").query(Long.class).single();
        String email="store-"+UUID.randomUUID()+"@example.test";
        String other="store-"+UUID.randomUUID()+"@example.test";
        db.sql("INSERT INTO app_user(email,password_hash) VALUES (?,'fixture'),(?,'fixture')").param(email).param(other).update();
        String auth="Bearer "+tokens.issue(email,"ROLE_USER");
        String second="Bearer "+tokens.issue(other,"ROLE_USER");
        http.perform(get(FAVORITES)).andExpect(status().isUnauthorized());
        http.perform(put(FAVORITES+"/"+id).servletPath(FAVORITES+"/"+id).header("Authorization",auth)).andExpect(status().isForbidden());
        for (int i=0; i<2; i++)
            http.perform(put(FAVORITES+"/"+id).servletPath(FAVORITES+"/"+id).header("Authorization",auth)
                    .header("Origin",origin).header("X-TCG-Request","1")).andExpect(status().isNoContent());
        http.perform(get(FAVORITES).header("Authorization",auth)).andExpect(status().isOk()).andExpect(jsonPath("$",hasSize(1)));
        http.perform(get(FAVORITES).header("Authorization",second)).andExpect(status().isOk()).andExpect(jsonPath("$",hasSize(0)));
        http.perform(get(FAVORITES+"/search")).andExpect(status().isUnauthorized());
        http.perform(get(FAVORITES+"/search").header("Authorization",auth)).andExpect(status().isOk()).andExpect(jsonPath("$.total").value(1));
        http.perform(get(FAVORITES+"/search").header("Authorization",second)).andExpect(status().isOk()).andExpect(jsonPath("$.total").value(0));
        for (int i=0; i<2; i++)
            http.perform(delete(FAVORITES+"/"+id).servletPath(FAVORITES+"/"+id).header("Authorization",auth)
                    .header("Origin",origin).header("X-TCG-Request","1")).andExpect(status().isNoContent());
        http.perform(get(FAVORITES).header("Authorization",auth)).andExpect(status().isOk()).andExpect(jsonPath("$",hasSize(0)));
    }

    @Test void laterQuarterHidesMissingLocationsAndRetainsDependentHistory() {
        long oldId=db.sql("SELECT id FROM store WHERE semas_id='MA0101202608A0104832'").query(Long.class).single();
        long uid=db.sql("INSERT INTO app_user(email,password_hash) VALUES (?,'fixture') RETURNING id")
                .param("store-"+UUID.randomUUID()+"@example.test").query(Long.class).single();
        db.sql("INSERT INTO favorite_store VALUES (?,?)").param(uid).param(oldId).update();
        String fixture="""
                [{"key":"MAFIXTURE00001","name":"Fixture","address":"fixture","region":"fixture",
                  "lon":127,"lat":37,"hours":{},"games":{"POKEMON":"https://example.invalid"}}]
                """;
        for (int i=0; i<2; i++)
            db.sql("SELECT apply_semas_directory(DATE '2026-12-31',cast(? AS jsonb))").param(fixture).query((rs,n)->true).single();
        assertFalse(db.sql("SELECT listed FROM store WHERE id=?").param(oldId).query(Boolean.class).single());
        assertEquals(1,db.sql("SELECT count(*) FROM favorite_store WHERE user_id=? AND store_id=?")
                .param(uid).param(oldId).query(Integer.class).single());
        assertEquals(1,db.sql("SELECT count(*) FROM store WHERE listed AND semas_id IS NOT NULL").query(Integer.class).single());
    }
}
