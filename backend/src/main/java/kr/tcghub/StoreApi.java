package kr.tcghub;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.constraints.*;
import java.security.Principal;
import java.time.LocalDate;
import java.util.List;
import java.util.HashMap;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/v1")
@Transactional(readOnly=true)
class StoreApi {
    record Shop(long id, String name, String address, String region, double lon, double lat,
                Double distanceKm, LocalDate sourceDate, String sourceUrl, JsonNode hours, JsonNode games,
                Boolean official, JsonNode events) {}
    record Results(List<Shop> items, long total, int page, int size) {}
    private static final String SEMAS = "https://www.data.go.kr/data/15083033/fileData.do";
    private final JdbcClient db;
    private final ObjectMapper json;
    StoreApi(JdbcClient db, ObjectMapper json) { this.db=db; this.json=json; }

    @GetMapping({"/stores","/me/favorites/stores/search"})
    Results search(@RequestParam(defaultValue="") @Size(max=100) String q,
                   @RequestParam(defaultValue="") @Pattern(regexp="|YUGIOH|POKEMON|ONEPIECE|WEISS|NIVEL|RIFTBOUND") String game,
                   @RequestParam(required=false) Double lat, @RequestParam(required=false) Double lon,
                   @RequestParam(required=false) Double radiusKm,
                   @RequestParam(defaultValue="0") @Min(0) @Max(100000) int page,
                   @RequestParam(defaultValue="75") @Min(1) @Max(200) int size,
                   HttpServletRequest request, Principal user) {
        if ((lat==null)!=(lon==null) || (radiusKm!=null && lat==null) || (lat!=null &&
                (!Double.isFinite(lat) || Math.abs(lat)>90 || !Double.isFinite(lon) || Math.abs(lon)>180)) ||
                (radiusKm!=null && (!Double.isFinite(radiusKm) || radiusKm<=0 || radiusKm>500))) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST);
        }
        var params = new HashMap<String,Object>();
        String from = " FROM store s ";
        String where = " WHERE s.listed ";
        String distance = "NULL::float8";
        if (request.getRequestURI().endsWith("/me/favorites/stores/search")) {
            where += " AND EXISTS (SELECT FROM favorite_store f JOIN app_user u ON u.id=f.user_id " +
                    " WHERE f.store_id=s.id AND u.email=:email AND u.enabled) ";
            params.put("email",user.getName());
        }
        if (lat!=null) {
            from += " CROSS JOIN (SELECT ST_SetSRID(ST_MakePoint(:lon,:lat),4326)::geography AS pt) origin ";
            where += " AND ST_DWithin(s.location,origin.pt,:meters) ";
            distance="ST_Distance(s.location,origin.pt)/1000.0";
            params.put("lat",lat); params.put("lon",lon); params.put("meters",1000 * (radiusKm==null ? 10 : radiusKm));
        }
        if (!q.isBlank()) {
            where += " AND strpos(lower(s.name || ' ' || s.address),lower(:q))>0 ";
            params.put("q",q.strip());
        }
        if (!game.isEmpty()) {
            where += " AND EXISTS (SELECT FROM store_game g WHERE g.store_id=s.id AND g.game_code=:game) ";
            params.put("game",game);
        }
        long total=db.sql("SELECT count(*)"+from+where).params(params).query(Long.class).single();
        params.put("size",size); params.put("offset",(long)page*size);
        String select = """
            SELECT s.id,s.name,s.address,s.region,s.semas_id,s.source_date,s.hours::text,public_store_official(s.id,s.official) official,
                   coalesce((select jsonb_agg(jsonb_build_object('id',e.id,'title',e.title,'gameCode',e.game_code,
                       'startsAt',e.starts_at,'endsAt',e.ends_at) order by e.starts_at,e.id)
                       from calendar_event e where e.store_id=s.id and e.owner_id is null and e.category='TOURNAMENT'
                       and e.status='PUBLISHED' and coalesce(e.ends_at,e.starts_at)>=now()
                       and e.starts_at<now()+interval '7 days'),'[]')::text as events,
                   ST_X(s.location::geometry) AS lon,ST_Y(s.location::geometry) AS lat,
                   coalesce((SELECT jsonb_agg(jsonb_build_object('code',g.game_code,'source',g.evidence_url,
                       'checked',g.checked_on) ORDER BY g.game_code) FROM store_game g WHERE g.store_id=s.id),'[]')::text AS games,
            """;
        var shops=db.sql(select+distance+" AS distance "+from+where+" ORDER BY distance NULLS LAST,s.region,s.name,s.id LIMIT :size OFFSET :offset")
            .params(params).query((rs,n) -> {
                try {
                    return new Shop(rs.getLong("id"),rs.getString("name"),rs.getString("address"),rs.getString("region"),
                        rs.getDouble("lon"),rs.getDouble("lat"),rs.getObject("distance",Double.class),
                        rs.getObject("source_date",LocalDate.class),rs.getString("semas_id")==null ? null : SEMAS,
                        json.readTree(rs.getString("hours")),json.readTree(rs.getString("games")),
                        rs.getObject("official",Boolean.class),json.readTree(rs.getString("events")));
                } catch (com.fasterxml.jackson.core.JsonProcessingException e) { throw new IllegalStateException(e); }
            }).list();
        return new Results(shops,total,page,size);
    }

    @GetMapping("/me/favorites/stores")
    List<Long> favorites(Principal user) {
        return db.sql("""
                SELECT f.store_id FROM favorite_store f JOIN app_user u ON f.user_id=u.id JOIN store s ON f.store_id=s.id
                WHERE u.email=? AND u.enabled AND s.listed ORDER BY f.store_id
                """).param(user.getName()).query(Long.class).list();
    }

    @PutMapping("/me/favorites/stores/{id}")
    @Transactional
    @ResponseStatus(HttpStatus.NO_CONTENT)
    void add(@PathVariable @Positive long id, Principal user) {
        var store = db.sql("SELECT id FROM store WHERE id=? AND listed FOR SHARE").param(id).query(Long.class).optional();
        if (store.isEmpty()) throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        long uid = db.sql("SELECT id FROM app_user WHERE email=? AND enabled").param(user.getName()).query(Long.class)
                .optional().orElseThrow(() -> new ResponseStatusException(HttpStatus.FORBIDDEN));
        db.sql("INSERT INTO favorite_store(user_id,store_id) VALUES (?,?) ON CONFLICT DO NOTHING").param(uid).param(id).update();
    }

    @DeleteMapping("/me/favorites/stores/{id}")
    @Transactional
    @ResponseStatus(HttpStatus.NO_CONTENT)
    void remove(@PathVariable @Positive long id, Principal user) {
        db.sql("DELETE FROM favorite_store f USING app_user u WHERE f.user_id=u.id AND u.email=? AND u.enabled AND f.store_id=?")
                .param(user.getName()).param(id).update();
    }
}
