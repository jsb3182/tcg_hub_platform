package kr.tcghub;

import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.security.Principal;
import java.sql.Types;
import java.time.OffsetDateTime;
import java.util.*;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/v1/admin/stores")
@Transactional
class StoreAdminApi {
    record Edit(@NotBlank @Size(max=160) String name,@NotBlank @Size(max=300) String address,
                @NotBlank @Size(max=60) String region,@NotNull @DecimalMin("-90") @DecimalMax("90") Double lat,
                @NotNull @DecimalMin("-180") @DecimalMax("180") Double lon,
                @NotNull @Size(max=6) Set<@NotBlank @Size(max=32) String> gameCodes,
                Boolean official,@NotNull Boolean listed,@Positive Integer version) {}
    record Shop(long id,String name,String address,String region,double lat,double lon,List<String> gameCodes,
                Boolean official,boolean listed,int version) {}
    record Saved(long id,int version) {}
    record Event(@NotBlank @Size(max=180) String title,@NotBlank @Size(max=32) String gameCode,
                 @NotNull OffsetDateTime startsAt,OffsetDateTime endsAt) {}
    private final JdbcClient db;
    StoreAdminApi(JdbcClient db) { this.db=db; }

    @GetMapping @Transactional(readOnly=true)
    List<Shop> shops(@RequestParam(defaultValue="") @Size(max=100) String q,
                     @RequestParam(defaultValue="0") @Min(0) @Max(1000000) int page) {
        return db.sql("""
            select s.*,ST_Y(location::geometry) lat,ST_X(location::geometry) lon,
                array(select game_code from store_game where store_id=s.id order by game_code) games
            from store s where strpos(lower(name || ' ' || address),lower(?))>0 order by name,id limit 50 offset ?
            """).param(q.strip()).param(page*50L).query((r,n)->new Shop(r.getLong("id"),r.getString("name"),
                r.getString("address"),r.getString("region"),r.getDouble("lat"),r.getDouble("lon"),
                List.of((String[])r.getArray("games").getArray()),r.getObject("official",Boolean.class),
                r.getBoolean("listed"),r.getInt("edit_version"))).list();
    }
    @PostMapping @ResponseStatus(HttpStatus.CREATED)
    Saved create(@RequestBody @Valid Edit edit,Principal user) { return save(null,edit,user); }
    @PutMapping("/{id}")
    Saved update(@PathVariable @Positive long id,@RequestBody @Valid Edit edit,Principal user) { return save(id,edit,user); }

    private Saved save(Long id,Edit edit,Principal user) {
        if (!Double.isFinite(edit.lat()) || !Double.isFinite(edit.lon())) throw badRequest();
        if (!edit.gameCodes().isEmpty() && db.sql("select count(*) from game where code in (:codes)")
                .param("codes",edit.gameCodes()).query(Long.class).single()!=edit.gameCodes().size()) throw badRequest();
        String fields="ST_SetSRID(ST_MakePoint(:lon,:lat),4326)::geography";
        var query=id==null ? db.sql("insert into store(name,address,region,location,official,listed) values(:name,:address,:region,"
                    +fields+",:official,:listed) returning id,edit_version as version") :
                db.sql("update store set name=:name,address=:address,region=:region,location="+fields+
                    ",official=:official,listed=:listed,edit_version=edit_version+1 where id=:id and edit_version=:v returning id,edit_version as version")
                    .param("id",id).param("v",edit.version(),Types.INTEGER);
        var saved=query.param("name",edit.name().strip()).param("address",edit.address().strip()).param("region",edit.region().strip())
                .param("lon",edit.lon()).param("lat",edit.lat()).param("official",edit.official(),Types.BOOLEAN)
                .param("listed",edit.listed()).query(Saved.class).optional().orElseThrow(()->new ResponseStatusException(HttpStatus.CONFLICT));
        if (edit.gameCodes().isEmpty()) db.sql("delete from store_game where store_id=?").param(saved.id()).update();
        else {
            db.sql("delete from store_game where store_id=:id and game_code not in (:codes)")
                    .param("id",saved.id()).param("codes",edit.gameCodes()).update();
            db.sql("insert into store_game(store_id,game_code) select :id,code from game where code in (:codes) on conflict do nothing")
                    .param("id",saved.id()).param("codes",edit.gameCodes()).update();
        }
        audit(user,id==null ? "CREATE_STORE" : "EDIT_STORE",saved.id());
        return saved;
    }

    @PostMapping("/{id}/events") @ResponseStatus(HttpStatus.CREATED)
    Map<String,Long> event(@PathVariable @Positive long id,@RequestBody @Valid Event event,Principal user) {
        if (event.endsAt()!=null && event.endsAt().isBefore(event.startsAt())) throw badRequest();
        long eventId=db.sql("""
                insert into calendar_event(store_id,game_code,title,category,starts_at,ends_at,status)
                select s.id,g.code,?,'TOURNAMENT',?,?,'PUBLISHED' from store s cross join game g where s.id=? and g.code=?
                returning id
                """).param(event.title().strip()).param(event.startsAt()).param(event.endsAt())
                .param(id).param(event.gameCode()).query(Long.class).optional().orElseThrow(StoreAdminApi::badRequest);
        audit(user,"ADD_STORE_EVENT",eventId);
        return Map.of("id",eventId);
    }
    private static ResponseStatusException badRequest() { return new ResponseStatusException(HttpStatus.BAD_REQUEST); }
    private void audit(Principal user,String action,long id) {
        db.sql("insert into operator_action(user_id,action,target_id) select id,?,? from app_user where email=?")
                .param(action).param(id).param(user.getName()).update();
    }
}
