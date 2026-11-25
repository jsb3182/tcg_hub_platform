package kr.tcghub;

import java.util.List;
import jakarta.validation.constraints.*;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/play")
@Transactional(readOnly = true)
class PlayApi {
    record CardLabel(long id, String name, String language, String number) {}

    private final JdbcClient db;
    PlayApi(JdbcClient db) { this.db = db; }

    @GetMapping("/cards")
    List<CardLabel> cards(@RequestParam @Pattern(regexp="YUGIOH|POKEMON") String game,
                          @RequestParam(defaultValue="ko") @Pattern(regexp="ko|en|ja") String lang,
                          @RequestParam(defaultValue="") @Size(max=100) String q,
                          @RequestParam(required=false) @Size(min=1,max=150) List<@Positive Long> ids) {
        String select = """
                select id, coalesce(nullif(specs->'names'->>:lang,''),name) as name,
                       case when nullif(specs->'names'->>:lang,'') is not null then :lang
                            else coalesce(specs->>'language','und') end as language, number
                  from card where status='PUBLISHED' and game_code=:game
                """;
        if (ids != null) {
            return db.sql(select + " and id in (:ids) order by id").param("ids",ids)
                    .param("lang",lang).param("game",game).query(CardLabel.class).list();
        }
        return db.sql(select + """
                 and (:q='' or strpos(lower(concat_ws(' ',name,number,specs->'names'->>'ko',
                           specs->'names'->>'en',specs->'names'->>'ja')),lower(:q))>0)
                 order by (coalesce(jsonb_exists(specs->'names',:lang),false) or coalesce(specs->>'language'=:lang,false)) desc,id
                 limit 30
                """)
                .param("game",game).param("lang",lang).param("q",q.strip()).query(CardLabel.class).list();
    }
}
