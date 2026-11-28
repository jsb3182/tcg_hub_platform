package kr.tcghub;

import java.util.Optional;
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
        String getNameBasis();
        String getNameReferenceUrl();
        String getEffectLanguage();
        String getEffectReferenceUrl();
        String getEffectBasis();
        String getImageUrl();
        String getImageBasis();
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
    @Query(value=SELECT + " where c.status='PUBLISHED' and c.id in (:ids) and (:game='' or c.game_code=:game) order by c.id", nativeQuery=true)
    java.util.List<Summary> publishedByIds(@Param("ids") java.util.List<Long> ids,@Param("game") String game,@Param("lang") String lang);

    @Query(value=SELECT + " where c.status='PUBLISHED' and c.id=:id", nativeQuery=true)
    Optional<Summary> published(@Param("id") long id, @Param("lang") String lang);
}
