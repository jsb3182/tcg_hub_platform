package kr.tcghub;

import java.time.LocalDate;
import java.util.Collection;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ResponseStatusException;

@Component
class CatalogFacets {
    private static final Map<String,List<String>> KEYS = Map.of(
        "YUGIOH", List.of("attribute","race","level","rank","link","atk","def"),
        "POKEMON", List.of("type","stage","energyType","hp","regulation"),
        "WEISS", List.of("type","color","level","cost","power","soul"),
        "ONEPIECE", List.of("type","color","attribute","traits","cost","power","life"),
        "NIVEL", List.of("type","attribute","cost","power","hit"),
        "RIFTBOUND", List.of("type","domain","energy","might","power")
    );
    record Options(List<Integer> years, List<String> traitKeys, List<String> values) {}

    private final JdbcClient db;
    CatalogFacets(JdbcClient db) { this.db=db; }

    void checkKey(String game,String key) {
        if (!key.isEmpty() && !KEYS.getOrDefault(game,List.of()).contains(key))
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"이 종목에서 사용할 수 없는 검색 항목입니다.");
    }

    Options options(String game,String key) {
        checkKey(game,key);
        var years=db.sql("""
            select distinct extract(year from dated)::int as year from (
                select distinct release_date as dated from card where status='PUBLISHED'
                    and (:game='' or game_code=:game) and release_date is not null
                union all
                select pd.release_date from catalog_pack_date pd where (:game='' or pd.game_code=:game)
                    and exists (select 1 from card c where c.pack_id=pd.pack_id and c.release_date is null and c.status='PUBLISHED')
            ) dates order by year desc
            """).param("game",game).query(Integer.class).list();
        List<String> values=key.isEmpty() ? List.of() : db.sql("""
            select val from (select distinct v.val from catalog_search_cache c
                cross join lateral jsonb_array_elements_text(c.facets->cast(:key as text)) v(val)
                where c.game_code=:game) options
            order by case when val ~ '^[0-9]{1,8}$' then val::int end nulls last,val
            """).param("game",game).param("key",key).query(String.class).list();
        return new Options(years,KEYS.getOrDefault(game,List.of()),values);
    }

    Map<Long,LocalDate> productDates(Collection<CardRepository.Summary> cards) {
        var ids=cards.stream().filter(card->card.getReleaseDate()==null && card.getPackId()!=null)
                .map(CardRepository.Summary::getPackId).distinct().toList();
        if (ids.isEmpty()) return Map.of();
        var dates=new HashMap<Long,LocalDate>();
        db.sql("select pack_id,release_date from catalog_pack_date where pack_id in (:ids)").param("ids",ids)
                .query((row,n)->Map.entry(row.getLong(1),row.getObject(2,LocalDate.class))).list()
                .forEach(entry->dates.put(entry.getKey(),entry.getValue()));
        return dates;
    }
}
