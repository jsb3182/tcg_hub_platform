package kr.tcghub;

import java.util.Optional;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.Repository;
import org.springframework.data.repository.query.Param;

interface CardRepository extends Repository<Card, Long> {
    interface Summary {
        long getId();
        String getGameCode();
        Long getPackId();
        String getPackName();
        String getName();
        String getOriginalName();
        String getNumber();
        String getRarity();
        String getEffect();
        String getLanguage();
        String getEffectLanguage();
        String getImageUrl();
        String getImageLanguage();
        String getProductCode();
        String getImageProduct();
        String getImageSource();
        Integer getCurveValue();
        java.time.LocalDate getReleaseDate();
        String getSourceUrl();
        String getSourceName();
    }
    String SELECT = """
        select c.id, c.game_code as "gameCode", c.pack_id as "packId", p.name as "packName",
               c.original_name as "originalName", c.number, c.rarity, card_curve_value(c.game_code,c.specs) as "curveValue",
        """ + CardEdition.FIELDS + """
               ,
               c.release_date as "releaseDate", coalesce(c.source_url,linked.source_url) as "sourceUrl", src.label as "sourceName"
          from card c left join pack p on p.id=c.pack_id left join feed_source src on src.id=c.source_id
        """ + CardEdition.JOIN;
    String FILTER = """
         where c.status='PUBLISHED' and (:game='' or c.game_code=:game)
           and (cast(:packId as bigint) is null or c.pack_id=:packId)
           and (:rarity='' or lower(c.rarity)=lower(:rarity)
             or lower(:rarity)=any(regexp_split_to_array(lower(c.rarity),'[[:space:]]+'))
             or exists (select 1 from card_variant v where v.card_id=c.id
                 and (lower(v.rarity)=lower(:rarity)
                      or lower(:rarity)=any(regexp_split_to_array(lower(v.rarity),'[[:space:]]+')))))
           and (:q='' or strpos(lower(concat_ws(' ',c.name,c.original_name,c.number,c.effect,
               c.specs->'names'->>'ko',c.specs->'names'->>'en',c.specs->'names'->>'ja',
               linked.names->>'ko',linked.names->>'en',linked.names->>'ja')),lower(:q))>0)
        """;

    @Query(value=SELECT + FILTER + " order by c.id", countQuery="select count(*) from card c" + CardEdition.LEGACY_JOIN + FILTER, nativeQuery=true)
    Page<Summary> search(@Param("game") String game, @Param("packId") Long packId, @Param("lang") String lang,
                         @Param("rarity") String rarity, @Param("q") String q, Pageable pageable);

    @Query(value=SELECT + " where c.status='PUBLISHED' and c.id=:id", nativeQuery=true)
    Optional<Summary> published(@Param("id") long id, @Param("lang") String lang);
}
