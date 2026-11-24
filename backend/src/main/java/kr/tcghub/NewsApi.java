package kr.tcghub;

import java.time.OffsetDateTime;
import java.util.List;
import jakarta.validation.constraints.*;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1")
@Transactional(readOnly=true)
class NewsApi {
    record Item(long id, String gameCode, String sourceName, String provider, String title, String summary,
                String sourceUrl, OffsetDateTime publishedAt, OffsetDateTime collectedAt) {}
    record Results(List<Item> items, int page, int size, long total) {}

    private final JdbcClient db;
    NewsApi(JdbcClient db) { this.db = db; }

    @GetMapping("/news")
    Results news(@RequestParam(defaultValue="") @Size(max=32) String game,
                 @RequestParam(defaultValue="0") @Min(0) @Max(1000000) int page,
                 @RequestParam(defaultValue="20") @Min(1) @Max(100) int size) {
        return items("PUBLISHED",game,page,size);
    }

    @GetMapping("/admin/review")
    Results candidates(@RequestParam(defaultValue="0") @Min(0) @Max(1000000) int page,
                       @RequestParam(defaultValue="20") @Min(1) @Max(100) int size) {
        return items("PENDING","",page,size);
    }

    private Results items(String status, String game, int page, int size) {
        String from = """
                from feed_item i join feed_source s on s.id=i.source_id
                where i.status=:status and i.payload->>'kind'='NEWS'
                  and (:game='' or coalesce(i.payload->>'gameCode',s.game_code)=:game)
                """;
        var total = db.sql("select count(*) " + from).param("status",status).param("game",game).query(Long.class).single();
        var rows = db.sql("""
                select i.id,coalesce(i.payload->>'gameCode',s.game_code) as game_code,
                       coalesce(s.label,s.source_key) as source_name,s.provider,i.payload->>'title' as title,
                       i.payload->>'summary' as summary,i.source_url,i.source_published_at as published_at,i.collected_at
                """ + from + " order by coalesce(i.source_published_at,i.collected_at) desc,i.id desc limit :size offset :offset")
                .param("status",status).param("game",game).param("size",size).param("offset",(long)page*size)
                .query(Item.class).list();
        return new Results(rows,page,size,total);
    }
}
