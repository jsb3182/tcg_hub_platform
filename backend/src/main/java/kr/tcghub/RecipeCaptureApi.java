package kr.tcghub;

import jakarta.validation.constraints.PositiveOrZero;
import jakarta.validation.constraints.Pattern;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/** Atlas variants available to compare with a local Yu-Gi-Oh! deck screenshot. */
@RestController
@Transactional(readOnly = true)
class RecipeCaptureApi {
    private static final int PAGE_SIZE = 512;
    record Item(long cardId, long variantId, int artworkIndex, String name, String number,
                String type, String konamiId, CatalogApi.Image image) {}
    record Identity(String konamiId, long cardId, String name, String number, String type, Map<Integer,String> artworks) {}
    record Page(List<Item> items, Long next) {}

    private final JdbcClient db;

    RecipeCaptureApi(JdbcClient db) {
        this.db = db;
    }

    @GetMapping("/api/v1/cards/capture-index")
    Page index(@RequestParam(defaultValue = "0") @PositiveOrZero long after) {
        var items = db.sql("""
            SELECT c.id AS card_id, v.id AS variant_id, v.position,
                   coalesce(nullif(c.specs->'names'->>'ko',''),c.name) AS name, c.number,
                   coalesce(c.specs->>'konami_id',linked.konami_id::text) AS konami_id,
                   coalesce(c.specs->>'type',c.specs->>'k') AS type,
                   v.sheet_id,v.col_idx,v.row_idx,s.storage_key,s.cell_width,s.cell_height,
                   edition.language AS tile_language
              FROM card_variant v
              JOIN card c ON c.id = v.card_id
              JOIN image_sheet s ON s.id = v.sheet_id
            """ + LibraryImage.EDITION_JOIN + CardEdition.LEGACY_JOIN + """
             WHERE c.game_code = 'YUGIOH' AND c.status = 'PUBLISHED' AND NOT s.retired AND v.id > :after
             ORDER BY v.id LIMIT :limit
            """).param("after",after).param("limit",PAGE_SIZE + 1)
            .query((r,n) -> new Item(r.getLong("card_id"),r.getLong("variant_id"),r.getInt("position") + 1,
                    r.getString("name"),r.getString("number"),r.getString("type"),r.getString("konami_id"),
                    LibraryImage.read(r))).list();
        if (items.size() <= PAGE_SIZE) return new Page(items,null);
        var page = items.subList(0,PAGE_SIZE);
        return new Page(page,page.get(PAGE_SIZE - 1).variantId());
    }

    // Resolve only the shortlisted artwork identities into a published local printing. Artwork IDs
    // from the external fingerprint index and local variant primary keys are separate namespaces.
    @GetMapping("/api/v1/cards/capture-identities")
    List<Identity> identities(@RequestParam @Pattern(regexp="[1-9][0-9]{0,8}(,[1-9][0-9]{0,8}){0,99}") String ids) {
        var keys = Arrays.stream(ids.split(",")).distinct().toList();
        var identities = new LinkedHashMap<String,Identity>();
        db.sql("""
                WITH printings AS (SELECT DISTINCT ON (cid) cid,c.id,coalesce(nullif(c.specs->'names'->>'ko',''),c.name) AS name,
                       c.number,coalesce(c.specs->>'type',c.specs->>'k') AS type
                  FROM card c
                """ + CardEdition.LEGACY_JOIN + """
                 CROSS JOIN LATERAL (SELECT coalesce(c.specs->>'konami_id',linked.konami_id::text) AS cid) matched
                 WHERE c.game_code='YUGIOH' AND c.status='PUBLISHED' AND cid IN (:ids)
                 ORDER BY cid,(linked.card_id is not null) DESC,c.id)
                SELECT p.*,n.artwork,n.image_path FROM printings p LEFT JOIN neuron_artwork n ON n.cid=p.cid
                ORDER BY p.cid,n.artwork
                """).param("ids",keys).query(rows -> {
                    while (rows.next()) {
                        var cid = rows.getString("cid");
                        var card = identities.get(cid);
                        if (card==null) {
                            card = new Identity(cid,rows.getLong("id"),rows.getString("name"),rows.getString("number"),
                                    rows.getString("type"),new LinkedHashMap<>());
                            identities.put(cid,card);
                        }
                        if (rows.getString("image_path")!=null) {
                            card.artworks().put(rows.getInt("artwork"),"https://artworks-jp-n.ygoresources.com"+rows.getString("image_path"));
                        }
                    }
                    return identities.size();
                });
        return List.copyOf(identities.values());
    }
}
