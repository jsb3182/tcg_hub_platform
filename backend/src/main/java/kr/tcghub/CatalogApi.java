package kr.tcghub;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.List;
import java.util.HashMap;
import com.fasterxml.jackson.annotation.JsonUnwrapped;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.validation.constraints.*;
import org.springframework.data.domain.PageRequest;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/v1")
@Transactional(readOnly = true)
class CatalogApi {
    record Game(String id, String code, String name) {}
    record Pack(long id, String gameCode, String code, String name, String releaseLabel, String bannerUrl) {}
    record ListedCard(@JsonUnwrapped CardRepository.Summary card, Image image) {}
    record PageResult(List<ListedCard> items, int page, int size, long total) {}
    record Image(long sheetId, int col, int row, String url, int cellWidth, int cellHeight) {}
    record Variant(long id, String rarity, Image image) {}
    record Details(@JsonUnwrapped CardRepository.Summary card, JsonNode specs, List<Variant> variants) {}

    private final CardRepository cards;
    private final JdbcClient db;
    private final ObjectMapper json;

    CatalogApi(CardRepository cards, JdbcClient db, ObjectMapper json) {
        this.cards = cards;
        this.db = db;
        this.json = json;
    }

    @GetMapping("/games")
    List<Game> games() {
        return db.sql("select code as id, code, name from game order by code").query(Game.class).list();
    }

    @GetMapping("/packs")
    List<Pack> packs(@RequestParam(defaultValue="") @Size(max=32) String game) {
        return db.sql("""
            select id, game_code, code, name, release_label, '/media/' || banner_key as banner_url
              from pack where (:game='' or game_code=:game) order by id
            """).param("game",game).query(Pack.class).list();
    }

    @GetMapping("/cards")
    PageResult list(@RequestParam(defaultValue="") @Size(max=32) String game,
                    @RequestParam(required=false) @Positive Long packId,
                    @RequestParam(defaultValue="") @Size(max=64) String rarity,
                    @RequestParam(defaultValue="") @Size(max=120) String q,
                    @RequestParam(defaultValue="0") @Min(0) @Max(1000000) int page,
                    @RequestParam(defaultValue="24") @Min(1) @Max(100) int size) {
        var result = cards.search(game, packId, rarity.strip(), q.strip(), PageRequest.of(page,size));
        var images = new HashMap<Long,Image>();
        if (!result.isEmpty()) {
            var ids = result.getContent().stream().map(CardRepository.Summary::getId).toList();
            db.sql("""
                select distinct on(v.card_id) v.card_id,v.sheet_id,v.col_idx,v.row_idx,s.storage_key,s.cell_width,s.cell_height
                from card_variant v join card c on c.id=v.card_id join image_sheet s on s.id=v.sheet_id
                where c.status='PUBLISHED' and not s.retired and v.card_id in (:ids) order by v.card_id,v.position
                """).param("ids",ids).query((r,n) -> java.util.Map.entry(r.getLong("card_id"),LibraryImage.read(r)))
                    .list().forEach(entry -> images.put(entry.getKey(),entry.getValue()));
        }
        var items = result.getContent().stream().map(card -> new ListedCard(card,images.get(card.getId()))).toList();
        return new PageResult(items,page,size,result.getTotalElements());
    }

    @GetMapping("/cards/{id}")
    Details details(@PathVariable @Positive long id) throws java.io.IOException {
        var card = cards.published(id).orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));
        var specs = db.sql("select specs::text from card where id=?").param(id).query(String.class).single();
        var variants = db.sql("""
            select v.id, v.rarity, v.sheet_id, v.col_idx, v.row_idx, s.storage_key, s.cell_width, s.cell_height
              from card_variant v left join image_sheet s on s.id=v.sheet_id and not s.retired
             where v.card_id=? order by v.position
            """).param(id).query((row, n) -> variant(row)).list();
        return new Details(card, json.readTree(specs), variants);
    }

    private static Variant variant(ResultSet row) throws SQLException {
        String key = row.getString("storage_key");
        Image image = key == null ? null : new Image(row.getLong("sheet_id"), row.getInt("col_idx"),
                row.getInt("row_idx"), "/media/" + key, row.getInt("cell_width"), row.getInt("cell_height"));
        return new Variant(row.getLong("id"), row.getString("rarity"), image);
    }
}
