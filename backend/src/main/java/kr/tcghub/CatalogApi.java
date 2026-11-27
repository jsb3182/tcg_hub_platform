package kr.tcghub;

import java.util.List;
import java.util.HashMap;
import java.time.LocalDate;
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
    record CatalogPack(long id,String gameCode,String code,String name,long catalogCount) {}
    record PackPage(List<CatalogPack> items,long total) {}
    record ListedCard(@JsonUnwrapped CardRepository.Summary card, Image image, LocalDate productReleaseDate) {}
    record PageResult(List<ListedCard> items, int page, int size, long total) {}
    record Image(long sheetId, int col, int row, String url, int cellWidth, int cellHeight, String language) {}
    record Variant(long id, String rarity, Image image) {}
    record Price(long variantId,String provider,String market,String sourceUrl,String currency,java.math.BigDecimal amount,
                 java.time.OffsetDateTime observedAt) {}
    record Details(@JsonUnwrapped CardRepository.Summary card, JsonNode specs, List<Variant> variants, LocalDate productReleaseDate,
                   List<Price> prices) {}

    private final CardRepository cards;
    private final JdbcClient db;
    private final ObjectMapper json;
    private final CatalogFacets facets;

    CatalogApi(CardRepository cards, JdbcClient db, ObjectMapper json, CatalogFacets facets) {
        this.cards = cards;
        this.db = db;
        this.json = json;
        this.facets = facets;
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

    @GetMapping("/catalog-packs")
    PackPage catalogPacks(@RequestParam(defaultValue="") @Pattern(regexp="|"+AdminCatalogApi.GAMES) String game,
                @RequestParam(defaultValue="") @Size(max=120) String q,
                @RequestParam(defaultValue="0") @Min(0) @Max(1000000) int page,
                @RequestParam(defaultValue="24") @Min(1) @Max(100) int size) {
        String from=" from pack p where (:game='' or p.game_code=:game) and (:q='' or strpos(lower(concat_ws(' ',p.name,p.code)),lower(:q))>0)";
        var total=db.sql("select count(*)"+from).param("game",game).param("q",q.strip()).query(Long.class).single();
        var items=db.sql("select p.id,p.game_code,p.code,p.name,(select count(*) from card c where c.pack_id=p.id and c.status='PUBLISHED') as catalog_count"+
                from+" order by p.release_date desc nulls last,p.id limit :size offset :offset").param("game",game).param("q",q.strip())
                .param("size",size).param("offset",(long)page*size).query(CatalogPack.class).list();
        return new PackPage(items,total);
    }

    @GetMapping(value="/cards",params="!ids")
    PageResult list(@RequestParam(defaultValue="") @Size(max=32) String game,
                    @RequestParam(defaultValue="ko") @Pattern(regexp="ko|en|ja") String lang,
                    @RequestParam(required=false) @Positive Long packId,
                    @RequestParam(defaultValue="") @Size(max=64) String rarity,
                    @RequestParam(defaultValue="") @Pattern(regexp="|NEW|REPRINT|NEW_ART") String inclusion,
                    @RequestParam(defaultValue="") @Pattern(regexp="|MONSTER|SPELL|TRAP") String ygoType,
                    @RequestParam(defaultValue="") @Size(max=120) String q,
                    @RequestParam(required=false) @Min(1900) @Max(9998) Integer releaseYear,
                    @RequestParam(defaultValue="") @Size(max=32) String traitKey,
                    @RequestParam(defaultValue="") @Size(max=80) String traitValue,
                    @RequestParam(defaultValue="0") @Min(0) @Max(1000000) int page,
                    @RequestParam(defaultValue="24") @Min(1) @Max(100) int size) {
        facets.checkKey(game,traitKey);
        if (traitKey.isEmpty()!=traitValue.isBlank())
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"검색 항목과 값을 함께 선택해 주세요.");
        LocalDate start = releaseYear==null ? null : LocalDate.of(releaseYear,1,1);
        var result = cards.search(game, packId, lang, rarity.strip(), inclusion, ygoType, q.strip(),
                start, start==null ? null : start.plusYears(1), traitKey, traitValue.strip(), PageRequest.of(page,size));
        return new PageResult(withImages(result.getContent(),lang),page,size,result.getTotalElements());
    }

    @GetMapping("/cards/facets")
    CatalogFacets.Options options(@RequestParam(defaultValue="") @Pattern(regexp="|YUGIOH|POKEMON|WEISS|ONEPIECE|RIFTBOUND|NIVEL") String game,
                                 @RequestParam(defaultValue="") @Size(max=32) String traitKey) {
        return facets.options(game,traitKey);
    }

    @GetMapping(value="/cards",params="ids")
    PageResult byIds(@RequestParam @Size(min=1,max=100) List<@Positive Long> ids,
                     @RequestParam(defaultValue="") @Size(max=32) String game,
                     @RequestParam(defaultValue="ko") @Pattern(regexp="ko|en|ja") String lang) {
        var found=cards.publishedByIds(ids,game,lang);
        return new PageResult(withImages(found,lang),0,ids.size(),found.size());
    }

    private List<ListedCard> withImages(List<CardRepository.Summary> summaries,String lang){
        var images = new HashMap<Long,Image>();
        if (!summaries.isEmpty()) {
            var ids = summaries.stream().map(CardRepository.Summary::getId).toList();
            db.sql("select c.id" + LibraryImage.COLUMNS + " from card c " + LibraryImage.LOCALIZED_JOIN
                    + " where c.id in (:ids) and tile.sheet_id is not null")
                    .param("ids",ids).param("lang",lang).query((r,n) -> java.util.Map.entry(r.getLong("id"),LibraryImage.read(r)))
                    .list().forEach(entry -> images.put(entry.getKey(),entry.getValue()));
        }
        var dates=facets.productDates(summaries);
        return summaries.stream().map(card -> new ListedCard(card,images.get(card.getId()),
                card.getReleaseDate()==null && card.getPackId()!=null ? dates.get(card.getPackId()) : null)).toList();
    }

    @GetMapping("/cards/{id}")
    Details details(@PathVariable @Positive long id,
                    @RequestParam(defaultValue="ko") @Pattern(regexp="ko|en|ja") String lang) throws java.io.IOException {
        var card = cards.published(id,lang).orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));
        var specs = db.sql("""
                select cast(((case when linked.card_id is null then c.specs else c.specs || jsonb_build_object(
                    'names', linked.names || case when jsonb_typeof(c.specs->'names')='object' then c.specs->'names' else '{}' end,
                    'texts', linked.texts || case when jsonb_typeof(c.specs->'texts')='object' then c.specs->'texts' else '{}' end
                ) end) - 'koreanPrinting' - 'wikiReferences' - 'readingOriginal' - 'images' - 'representativeArt')
                || jsonb_build_object('images',jsonb_strip_nulls(jsonb_build_object(
                    'ko',local_catalog_art(c.id,c.specs->'images'->>'ko'),
                    'en',local_catalog_art(c.id,c.specs->'images'->>'en'),
                    'ja',local_catalog_art(c.id,c.specs->'images'->>'ja'))))
                || case when kr_read.name is not null or kr_read.effect is not null then
                    jsonb_build_object('readingOriginal',jsonb_strip_nulls(jsonb_build_object(
                        'language',c.specs->>'language','name',c.name,'effect',c.effect))) else '{}'::jsonb end
                || case when wiki.lookup_key is null then '{}'::jsonb else jsonb_build_object('wikiReferences',
                    jsonb_build_array(jsonb_strip_nulls(jsonb_build_object('title',wiki.title,'url',wiki.document_url,
                        'revision',wiki.revision,'snapshotDate',wiki.snapshot_date,'snapshotUrl',wiki.snapshot_url,
                        'snapshotRow',wiki.snapshot_row,'articleSha256',wiki.article_sha256,
                        'verificationUrl',wiki.verification_url,'language','ko','facts',wiki.facts,'details',wiki.article_details)))) end
                || case when kr.konami_id is null then '{}'::jsonb
                  else jsonb_build_object('koreanPrinting',jsonb_strip_nulls(jsonb_build_object(
                    'number',kr.number,'productReleasedOn',kr.product_released_on,
                    'cardUrl','https://www.db.yugioh-card.com/yugiohdb/card_search.action?ope=2&request_locale=ko&cid='||kr.konami_id,
                    'printingSourceUrl','https://github.com/DawnbrandBots/yaml-yugi/blob/'||kr.yaml_revision||'/data/cards/'||kr.yaml_file,
                    'productSourceUrl','https://github.com/iconmaster5326/YGOJSON/blob/ab5016e14cc6c3296a85d52de2c8b61b9db55cfa/sets/'||kr.product_id||'.json'
                  ))) end as text) from card c
                """ + CardEdition.LEGACY_JOIN + """
                left join feed_source origin on origin.id=c.source_id
                left join yugioh_korean_print kr on c.game_code='YUGIOH' and kr.konami_id=case
                    when starts_with(c.legacy_key,'catalog:YUGIOH:') and origin.provider='CATALOG' and origin.source_key='YUGIOH'
                      and c.specs->>'konami_id' ~ '^[1-9][0-9]{0,9}$' then (c.specs->>'konami_id')::bigint
                    when starts_with(c.legacy_key,'legacy:') then linked.konami_id end
                where c.id=?
                """).param(id).query(String.class).single();
        var variants = db.sql("""
            select v.id, v.rarity, v.sheet_id, v.col_idx, v.row_idx, s.storage_key, s.cell_width, s.cell_height,
                   edition.language as tile_language
              from card_variant v left join image_sheet s on s.id=v.sheet_id and not s.retired
            """ + LibraryImage.EDITION_JOIN + " where v.card_id=? order by v.position")
                .param(id).query((row, n) -> new Variant(row.getLong("id"),row.getString("rarity"),LibraryImage.read(row))).list();
        var dates=facets.productDates(List.of(card));
        var prices=db.sql("""
            select l.variant_id,l.provider,l.market,l.source_url,s.currency,s.amount,s.observed_at
            from card_variant v join price_listing l on l.variant_id=v.id
            cross join lateral (select currency,amount,observed_at from price_snapshot where listing_id=l.id
                                order by observed_at desc limit 1) s
            where v.card_id=? order by s.observed_at desc,l.id limit 50
            """).param(id).query(Price.class).list();
        return new Details(card, json.readTree(specs), variants, card.getPackId()==null ? null : dates.get(card.getPackId()),prices);
    }

}
