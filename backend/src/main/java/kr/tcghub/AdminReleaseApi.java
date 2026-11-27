package kr.tcghub;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.net.URI;
import java.security.Principal;
import java.time.LocalDate;
import java.util.*;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/v1/admin/releases")
@Transactional(readOnly=true)
class AdminReleaseApi {
    static final String REGIONS="KR|JP|NA|EN|EU|GLOBAL|CN|TCG";
    static final String TYPES="BOOSTER|STARTER|PROMO|ACCESSORY|SPECIAL|UNKNOWN";
    record Current(long version,String gameCode,String region) {}
    record Input(@NotNull @Pattern(regexp=AdminCatalogApi.GAMES) String gameCode,
                 @NotNull @Pattern(regexp=REGIONS) String region,@Size(max=96) String code,
                 @NotBlank @Size(max=400) String name, @Size(max=3) Map<@Pattern(regexp="ko|en|ja") String,@NotBlank @Size(max=400) String> names,
                 @NotNull LocalDate releaseDate,@NotBlank @Size(max=2048) String sourceUrl,
                 @Positive Long catalogPackId,@NotNull @Pattern(regexp=TYPES) String productType,@Positive Long version) {}

    private final JdbcClient db;
    private final ReleaseCalendarApi calendar;
    private final ObjectMapper json;
    AdminReleaseApi(JdbcClient db,ReleaseCalendarApi calendar,ObjectMapper json) {
        this.db=db; this.calendar=calendar; this.json=json;
    }

    @GetMapping
    ReleaseCalendarApi.Result list(@RequestParam(defaultValue="") @Size(max=32) String game,
                    @RequestParam(defaultValue="") @Size(max=120) String q,
                    @RequestParam(defaultValue="0") @Min(0) @Max(1000000) int page,
                    @RequestParam(defaultValue="20") @Min(1) @Max(100) int size) {
        return calendar.list(game,"","","","all",q,null,page,size);
    }

    @PostMapping @Transactional @ResponseStatus(HttpStatus.CREATED)
    Map<String,Object> create(@Valid @RequestBody Input input,Principal actor) throws Exception {
        return save(null,input,actor);
    }
    @GetMapping("/{id}")
    Map<String,Object> get(@PathVariable @Positive long id) {
        return db.sql("""
            select e.id,e.game_code as "gameCode",e.region,e.code,e.name,e.names,
                e.release_date as "releaseDate",e.source_url as "sourceUrl",linked.pack_id as "catalogPackId",
                e.product_type as "productType",e.version,e.manual
                from product_release e
            """ + ReleaseCalendarApi.LINK + " where e.id=?").param(id).query((r,n)->{
                Map<String,Object> values=new LinkedHashMap<>();
                var fields=r.getMetaData();
                for (int i=1;i<=fields.getColumnCount();i++) values.put(fields.getColumnLabel(i),r.getObject(i));
                try {values.put("names",json.readTree(r.getString("names")));}
                catch (com.fasterxml.jackson.core.JsonProcessingException ex) {throw new java.sql.SQLException(ex);}
                return values;
            }).optional().orElseThrow(()->new ResponseStatusException(HttpStatus.NOT_FOUND));
    }
    @PutMapping("/{id}") @Transactional
    Map<String,Object> update(@PathVariable @Positive long id,@Valid @RequestBody Input input,Principal actor) throws Exception {
        return save(id,input,actor);
    }
    private Map<String,Object> save(Long id,Input input,Principal actor) throws Exception {
        URI url;
        try { url=URI.create(input.sourceUrl()); } catch (IllegalArgumentException e) { throw bad(); }
        if (url.getHost()==null || url.getUserInfo()!=null || !("https".equals(url.getScheme()) ||
                ("NIVEL".equals(input.gameCode()) && "http".equals(url.getScheme()) && "nivelarena.co.kr".equals(url.getAuthority())))) throw bad();
        if (input.catalogPackId()!=null && !db.sql("select exists(select 1 from pack where id=? and game_code=?)")
                .param(input.catalogPackId()).param(input.gameCode()).query(Boolean.class).single()) throw bad();
        if (id!=null) {
            var current=db.sql("select version,game_code,region from product_release where id=? for update").param(id)
                    .query(Current.class).optional().orElseThrow(()->new ResponseStatusException(HttpStatus.NOT_FOUND));
            if (!input.gameCode().equals(current.gameCode()) || !input.region().equals(current.region())) throw bad();
            if (input.version()==null || input.version()!=current.version())
                throw new ResponseStatusException(HttpStatus.CONFLICT);
        }
        String statement=id==null ? """
            insert into product_release(game_code,product_key,region,code,name,names,release_date,source_url,selected_pack_id,product_type,manual)
            values (:game,:key,:region,:code,:name,cast(:names as jsonb),:day,:url,:pack,:type,true) returning id,version
            """ : """
            update product_release set code=:code,name=:name,names=cast(:names as jsonb),release_date=:day,source_url=:url,
                selected_pack_id=:pack,catalog_code=null,catalog_name=null,manual=true,product_type=:type
            where id=:id returning id,version
            """;
        var names=input.names()==null ? Map.<String,String>of() : input.names();
        var sql=db.sql(statement).param("code",input.code()).param("name",input.name().strip()).param("names",json.writeValueAsString(names))
                .param("day",input.releaseDate()).param("url",url.toASCIIString()).param("pack",input.catalogPackId()).param("type",input.productType());
        if (id==null) sql=sql.param("game",input.gameCode()).param("key","manual:"+UUID.randomUUID()).param("region",input.region());
        else sql=sql.param("id",id);
        var stored=sql.query().singleRow();
        long admin=db.sql("select id from app_user where email=? and enabled and role='ROLE_ADMIN'").param(actor.getName())
                .query(Long.class).optional().orElseThrow(()->new ResponseStatusException(HttpStatus.FORBIDDEN));
        db.sql("insert into operator_action(user_id,action,target_id) values(?,?,?)")
                .param(admin).param(id==null?"CREATE_RELEASE":"EDIT_RELEASE").param(stored.get("id")).update();
        Map<String,Object> response=json.convertValue(input,new com.fasterxml.jackson.core.type.TypeReference<Map<String,Object>>(){});
        response.putAll(stored);
        return response;
    }
    private static ResponseStatusException bad() { return new ResponseStatusException(HttpStatus.BAD_REQUEST); }
}
