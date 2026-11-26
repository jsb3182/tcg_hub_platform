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
    record CardLabel(long id, String name, String language, String number, String effect, String effectLanguage,
                     String imageUrl, String imageLanguage, String productCode, String imageProduct, String imageSource,
                     String type, List<String> colors, CatalogApi.Image image) {}

    private final JdbcClient db;
    PlayApi(JdbcClient db) { this.db = db; }

    @GetMapping("/cards")
    List<CardLabel> cards(@RequestParam @Pattern(regexp="YUGIOH|POKEMON|ONEPIECE") String game,
                          @RequestParam(defaultValue="ko") @Pattern(regexp="ko|en|ja") String lang,
                          @RequestParam(defaultValue="") @Size(max=100) String q,
                          @RequestParam(required=false) @Size(min=1,max=150) List<@Positive Long> ids) {
        String select = "select c.id,c.number," + CardEdition.FIELDS + """
                ,coalesce(c.specs->>'type',c.specs->>'card_type',c.specs->>'k') as type,
                array(select jsonb_array_elements_text(case when jsonb_typeof(c.specs->'colors')='array'
                         then c.specs->'colors' else '[]'::jsonb end)) as colors
                """ + LibraryImage.COLUMNS + " from card c " + CardEdition.IMAGE_JOIN + LibraryImage.LOCALIZED_JOIN
                + " where c.status='PUBLISHED' and c.game_code=:game";
        org.springframework.jdbc.core.RowMapper<CardLabel> map = (r,n) -> new CardLabel(r.getLong("id"),r.getString("name"),
                r.getString("language"),r.getString("number"),r.getString("effect"),r.getString("effectLanguage"),
                r.getString("imageUrl"),r.getString("imageLanguage"),r.getString("productCode"),r.getString("imageProduct"),
                r.getString("imageSource"),r.getString("type"),List.of((String[])r.getArray("colors").getArray()),LibraryImage.read(r));
        if (ids != null) {
            return db.sql(select + " and id in (:ids) order by id").param("ids",ids)
                    .param("lang",lang).param("game",game).query(map).list();
        }
        return db.sql(select + """
                 and (:q='' or strpos(lower(concat_ws(' ',name,number,specs->'names'->>'ko',
                           specs->'names'->>'en',specs->'names'->>'ja')),lower(:q))>0)
                 order by (coalesce(jsonb_exists(specs->'names',:lang),false) or coalesce(specs->>'language'=:lang,false)) desc,id
                 limit 30
                """)
                .param("game",game).param("lang",lang).param("q",q.strip()).query(map).list();
    }
}
