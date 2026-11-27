package kr.tcghub;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.validation.constraints.*;
import java.sql.SQLException;
import java.time.LocalDate;
import java.time.YearMonth;
import java.time.ZoneId;
import java.util.*;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/release-calendar")
class ReleaseCalendarApi {
    record Item(long id, String gameCode, String productKey, String code, String name, JsonNode names,
                String region, LocalDate releaseDate, String sourceUrl, Long catalogPackId, long catalogCount,
                String productType, long version) {}
    record Result(List<Item> items, int page, int size, long total, LocalDate asOf) {}

    // An ambiguous printing code can name different products. Keep the announcement visible
    // and omit its card link until the source can distinguish the exact catalog product.
    static final String LINK = """
        left join lateral (
            select min(p.id) as pack_id from pack p
            where p.game_code=e.game_code and (p.id=e.selected_pack_id or (not e.manual and (e.catalog_code is not null or e.catalog_name is not null)
              and (e.catalog_code is null or upper(p.code)=upper(e.catalog_code))
              and (e.catalog_name is null or lower(p.name)=lower(e.catalog_name))
              and case when e.game_code='YUGIOH' and starts_with(e.product_key,'na-premiere:')
                    then p.metadata @> '{"wp":true,"sec":true}' else starts_with(p.legacy_key,'catalog:') end))
            having count(*)=1
        ) linked on true
        """;
    private final JdbcClient db;
    private final ObjectMapper json;
    ReleaseCalendarApi(JdbcClient db, ObjectMapper json) { this.db=db; this.json=json; }

    @GetMapping
    @Transactional(readOnly=true,isolation=Isolation.REPEATABLE_READ)
    Result list(@RequestParam(defaultValue="") @Size(max=80) String game,
                @RequestParam(defaultValue="") @Size(max=60) String region,
                @RequestParam(defaultValue="") @Size(max=80) String productType,
                @RequestParam(defaultValue="") @Pattern(regexp="|[1-9][0-9]{3}-(0[1-9]|1[0-2])") String month,
                @RequestParam(defaultValue="upcoming") @Pattern(regexp="upcoming|past|all") String period,
                @RequestParam(defaultValue="") @Size(max=120) String q,
                @RequestParam(required=false) @Positive Long packId,
                @RequestParam(defaultValue="0") @Min(0) @Max(1000000) int page,
                @RequestParam(defaultValue="24") @Min(1) @Max(100) int size) {
        LocalDate today=LocalDate.now(ZoneId.of("Asia/Seoul"));
        Map<String,Object> params=new HashMap<>();
        StringBuilder from=new StringBuilder(" from product_release e ");
        if (packId!=null) from.append(LINK);
        from.append(" where true ");
        addFilter(from,params,"e.game_code","games",game,Set.of("YUGIOH","POKEMON","WEISS","ONEPIECE","RIFTBOUND","NIVEL"));
        addFilter(from,params,"e.region","regions",region,Set.of("KR","JP","NA","EN","EU","GLOBAL","CN","TCG"));
        addFilter(from,params,"e.product_type","types",productType,Set.of("BOOSTER","STARTER","PROMO","ACCESSORY","SPECIAL","UNKNOWN"));
        if (!month.isEmpty()) {
            var first=YearMonth.parse(month).atDay(1);
            from.append(" and e.release_date>=:first and e.release_date<:next");
            params.put("first",first); params.put("next",first.plusMonths(1));
        }
        if (packId!=null) { from.append(" and linked.pack_id=:pack"); params.put("pack",packId); }
        if (!period.equals("all")) {
            from.append(period.equals("past") ? " and e.release_date<:today" : " and e.release_date>=:today");
            params.put("today",today);
        }
        if (!q.isBlank()) {
            from.append(" and strpos(lower(concat_ws(' ',e.name,e.code,e.names->>'ko',e.names->>'en',e.names->>'ja')),lower(:query))>0");
            params.put("query",q.strip());
        }
        long total=db.sql("select count(*)"+from).params(params).query(Long.class).single();
        String ordering=period.equals("upcoming") ? " order by e.release_date,e.id" : " order by e.release_date desc,e.id desc";
        params.put("size",size); params.put("offset",(long)page*size);
        // Resolve links and count cards only for the visible page on unfiltered catalog requests.
        String pageSql="select e.*"+(packId==null ? "" : ",linked.pack_id")+from+ordering+" limit :size offset :offset";
        String linkId=packId==null ? "linked.pack_id" : "e.pack_id";
        String sql="select e.*,"+linkId+" as card_pack_id,"+
            "(select count(*) from card c where c.pack_id="+linkId+" and c.status='PUBLISHED') as catalog_count from ("+pageSql+") e "+
            (packId==null ? LINK : "")+ordering;
        var items=db.sql(sql).params(params).query((r,n)->{
            JsonNode names;
            try { names=json.readTree(r.getString("names")); }
            catch (com.fasterxml.jackson.core.JsonProcessingException invalid) { throw new SQLException("Invalid product names",invalid); }
            return new Item(r.getLong("id"),r.getString("game_code"),r.getString("product_key"),r.getString("code"),
                r.getString("name"),names,r.getString("region"),r.getObject("release_date",LocalDate.class),
                r.getString("source_url"),r.getObject("card_pack_id",Long.class),r.getLong("catalog_count"),
                r.getString("product_type"),r.getLong("version"));
        }).list();
        return new Result(items,page,size,total,today);
    }

    private static void addFilter(StringBuilder sql,Map<String,Object> params,String column,String key,String input,Set<String> allowed) {
        if (input.isEmpty()) return;
        var values=Arrays.asList(input.split(",",-1));
        if (!allowed.containsAll(values))
            throw new org.springframework.web.server.ResponseStatusException(org.springframework.http.HttpStatus.BAD_REQUEST);
        sql.append(" and ").append(column).append(" in (:").append(key).append(")");
        params.put(key,new LinkedHashSet<>(values));
    }
}
