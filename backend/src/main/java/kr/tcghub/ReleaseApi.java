package kr.tcghub;

import com.fasterxml.jackson.annotation.JsonUnwrapped;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Positive;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.LocalDate;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/v1")
@Transactional(readOnly = true)
class ReleaseApi {
    record OfficialProduct(String englishName, LocalDate launchDate, LocalDate otsDate, int setSize, String sourceUrl) {}
    record Header(long id, String gameCode, String code, String name, LocalDate releaseDate,
                  String releaseLabel, String bannerUrl, String group, JsonNode metadata,
                  long total, long newCount, long reprintCount, long newArtCount, long productCount,
                  String firstProductDate, String lastProductDate, String latestProduct, OfficialProduct officialProduct) {}
    record Printing(long id, String name, String originalName, String language, String number,
                    String rarity, List<String> rarities, String type, String subtype, String inclusion,
                    String product, String productDate, LocalDate releaseDate, String effect,
                    String effectLanguage, String imageUrl, String imageLanguage, CatalogApi.Image image,
                    int variantCount, String nameBasis, String nameReferenceUrl, String imageBasis,
                    String imageSource, String imageProduct, String productCode, String effectReferenceUrl, String effectBasis) {}
    record PackDetail(@JsonUnwrapped Header header, List<Printing> cards, int page, int size, boolean hasMore) {}

    private static final Set<String> PUBLIC_METADATA = Set.of("id","code","kind","jp","kr","cnt","note","sec","sx","wp","bgp");

    // Both aggregate counters and individual card labels use the same evidence.
    private static final String INCLUSION = """
            case c.specs->>'nw' when '신규' then 'NEW' when '재록' then 'REPRINT'
                 when '신규 일러스트' then 'NEW_ART' end
            """;
    private static final String HEADER = """
            select p.id,p.game_code,p.code,p.name,p.release_date,p.release_label,
                   '/media/' || p.banner_key as banner_url,p.metadata::text as metadata,
                   case when p.metadata->>'sec' is distinct from 'true' then 'SCHEDULE'
                        when p.metadata->>'wp'='true' then 'PREMIERE'
                        when p.metadata->>'sx'='l' then 'ARCHIVE' else 'DISTRIBUTION' end as release_group,
                   n.english_name,n.launch_date,n.ots_date,n.set_size,n.source_url,totals.*
              from pack p
              left join yugioh_na_product n on p.game_code='YUGIOH' and n.code=p.code
                    and p.metadata @> '{"sec":true,"wp":true}'
              cross join lateral (
                select count(*) as total,
                       count(*) filter(where inclusion='NEW') as new_count,
                       count(*) filter(where inclusion='REPRINT') as reprint_count,
                       count(*) filter(where inclusion='NEW_ART') as new_art_count,
                       count(distinct product) as product_count,
                       min(dated) as first_product_date, max(dated) as last_product_date,
                       (array_agg(product order by dated desc,id desc) filter(where dated is not null))[1] as latest_product
                  from (
                    select c.id,nullif(c.specs->>'pr','') as product,
                           case when c.specs->>'pd' ~ '^[0-9]{4}-[0-9]{2}($|-)' then c.specs->>'pd' end as dated,
            """ + INCLUSION + """
                           as inclusion
                      from card c where c.pack_id=p.id and c.status='PUBLISHED'
                  ) printed
              ) totals
            """;

    private static final String PRINTINGS = """
            select c.id,c.number,c.original_name,c.rarity,c.release_date,
                   starts_with(c.legacy_key,'legacy:') as legacy_rarities,
                   coalesce(nullif(c.specs->>'k',''),nullif(c.specs->>'type',''),c.specs->>'card_type') as card_type,
                   nullif(c.specs->>'sub','') as subtype, nullif(c.specs->>'pr','') as product,
                   nullif(c.specs->>'pd','') as product_date,
                   array(select v.rarity from card_variant v where v.card_id=c.id order by v.position) as variants,
            """ + INCLUSION + " as inclusion," + CardEdition.FIELDS + LibraryImage.COLUMNS + """
              from card c
            """ + CardEdition.JOIN + LibraryImage.LOCALIZED_JOIN + """
             where c.pack_id=:id and c.status='PUBLISHED'
             order by c.id limit :size offset :offset
            """;

    private final JdbcClient db;
    private final ObjectMapper json;
    ReleaseApi(JdbcClient db, ObjectMapper json) {
        this.db = db;
        this.json = json;
    }

    @GetMapping("/releases")
    List<Header> releases() {
        return db.sql(HEADER + """
                 where starts_with(p.legacy_key,'legacy:') or p.release_date is not null
                    or nullif(btrim(p.release_label),'') is not null
                 order by p.id
                """).query((r,n) -> header(r)).list();
    }

    @GetMapping("/packs/{id}")
    @Transactional(readOnly = true, isolation = Isolation.REPEATABLE_READ)
    PackDetail pack(@PathVariable @Positive long id,
                    @RequestParam(defaultValue="ko") @Pattern(regexp="ko|en|ja") String lang,
                    @RequestParam(defaultValue="0") @Min(0) @Max(1000000) int page,
                    @RequestParam(defaultValue="200") @Min(1) @Max(200) int size) {
        Header pack = db.sql(HEADER + " where p.id=:id").param("id",id)
                .query((r,n) -> header(r)).optional()
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));
        long offset = (long) page * size;
        var cards = db.sql(PRINTINGS).param("id",id).param("lang",lang).param("size",size).param("offset",offset)
                .query((r,n) -> printing(r)).list();
        return new PackDetail(pack,cards,page,size,offset + cards.size() < pack.total());
    }

    private Header header(ResultSet row) throws SQLException {
        var metadata = json.createObjectNode();
        try {
            JsonNode stored = json.readTree(row.getString("metadata"));
            for (String key : PUBLIC_METADATA) {
                JsonNode value = stored.get(key);
                if (value != null && value.isValueNode()) metadata.set(key,value);
            }
        } catch (JsonProcessingException invalid) {
            throw new SQLException("Invalid pack metadata",invalid);
        }
        return new Header(row.getLong("id"),row.getString("game_code"),row.getString("code"),row.getString("name"),
                row.getObject("release_date",LocalDate.class),row.getString("release_label"),row.getString("banner_url"),
                row.getString("release_group"),metadata,row.getLong("total"),row.getLong("new_count"),
                row.getLong("reprint_count"),row.getLong("new_art_count"),row.getLong("product_count"),
                row.getString("first_product_date"),row.getString("last_product_date"),row.getString("latest_product"),
                row.getString("source_url")==null ? null : new OfficialProduct(row.getString("english_name"),
                    row.getObject("launch_date",LocalDate.class),row.getObject("ots_date",LocalDate.class),
                    row.getInt("set_size"),row.getString("source_url")));
    }

    private static Printing printing(ResultSet row) throws SQLException {
        String rarity = row.getString("rarity");
        String[] variants = (String[]) row.getArray("variants").getArray();
        var rarities = new LinkedHashSet<String>();
        boolean splitCodes = row.getBoolean("legacy_rarities");
        addRarities(rarities,rarity,splitCodes);
        for (String variant : variants) addRarities(rarities,variant,splitCodes);
        return new Printing(row.getLong("id"),row.getString("name"),row.getString("original_name"),
                row.getString("language"),row.getString("number"),rarity,List.copyOf(rarities),
                row.getString("card_type"),row.getString("subtype"),row.getString("inclusion"),
                row.getString("product"),row.getString("product_date"),row.getObject("release_date",LocalDate.class),
                row.getString("effect"),row.getString("effectLanguage"),row.getString("imageUrl"),
                row.getString("imageLanguage"),LibraryImage.read(row),variants.length,row.getString("nameBasis"),
                row.getString("nameReferenceUrl"),row.getString("imageBasis"),row.getString("imageSource"),
                row.getString("imageProduct"),row.getString("productCode"),row.getString("effectReferenceUrl"),
                row.getString("effectBasis"));
    }

    private static void addRarities(Set<String> rarities, String value, boolean splitCodes) {
        if (value == null || value.isBlank()) return;
        if (splitCodes) rarities.addAll(List.of(value.strip().split("\\s+")));
        else rarities.add(value.strip());
    }
}
