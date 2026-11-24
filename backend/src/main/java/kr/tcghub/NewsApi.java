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
                String sourceUrl, OffsetDateTime publishedAt, OffsetDateTime collectedAt, String originalTitle,
                String originalSummary, String originalLanguage, String contentLanguage, String summaryLanguage,
                String translationStatus) {}
    record Results(List<Item> items, int page, int size, long total) {}

    private final JdbcClient db;
    NewsApi(JdbcClient db) { this.db = db; }

    @GetMapping("/news")
    Results news(@RequestParam(defaultValue="") @Size(max=32) String game,
                 @RequestParam(defaultValue="0") @Min(0) @Max(1000000) int page,
                 @RequestParam(defaultValue="20") @Min(1) @Max(100) int size,
                 @RequestParam(required=false) @Pattern(regexp="ko|en|ja") String lang) {
        return items("PUBLISHED",game,page,size,lang == null ? "ko" : lang);
    }

    @GetMapping("/admin/review")
    Results candidates(@RequestParam(defaultValue="0") @Min(0) @Max(1000000) int page,
                       @RequestParam(defaultValue="20") @Min(1) @Max(100) int size,
                       @RequestParam(required=false) @Pattern(regexp="ko|en|ja") String lang) {
        return items("PENDING","",page,size,lang == null ? "ko" : lang);
    }

    private Results items(String status, String game, int page, int size, String lang) {
        String from = " from feed_item i join feed_source s on s.id=i.source_id ";
        String where = """
                where i.status=:status and i.payload->>'kind'='NEWS'
                  and (:game='' or coalesce(i.payload->>'gameCode',s.game_code)=:game)
                """;
        var total = db.sql("select count(*)" + from + where)
                .param("status",status).param("game",game).query(Long.class).single();
        var rows = db.sql("""
                select i.id,coalesce(i.payload->>'gameCode',s.game_code) as game_code,
                       coalesce(s.label,s.source_key) as source_name,s.provider,coalesce(t.title,i.payload->>'title') as title,
                       case when nullif(trim(t.summary),'') is not null then t.summary else i.payload->>'summary' end as summary,
                       i.source_url,i.source_published_at as published_at,i.collected_at,
                       i.payload->>'title' as original_title,i.payload->>'summary' as original_summary,i.original_language,
                       coalesce(t.lang,i.original_language) as content_language,
                       case when nullif(trim(t.summary),'') is not null then t.lang
                            when nullif(trim(i.payload->>'summary'),'') is not null then i.original_language end as summary_language,
                       case when t.item_id is not null then 'TRANSLATED'
                            when i.original_language=:lang then 'ORIGINAL' else 'PENDING' end as translation_status
                """ + from + """
                left join feed_item_translation t on t.item_id=i.id and t.lang=:lang
                     and t.lang is distinct from i.original_language
                """ + where + " order by coalesce(i.source_published_at,i.collected_at) desc,i.id desc limit :size offset :offset")
                .param("status",status).param("game",game).param("lang",lang).param("size",size).param("offset",(long)page*size)
                .query(Item.class).list();
        return new Results(rows,page,size,total);
    }
}
