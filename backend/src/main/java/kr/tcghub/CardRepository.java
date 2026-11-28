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
    String FILTER = """
         where c.status='PUBLISHED' and (:game='' or c.game_code=:game)
           and (not :withImage or c.id in (
                 select v.card_id from card_variant v join image_sheet s on s.id=v.sheet_id where not s.retired
                 union all
        """ + CardEdition.CARDS_WITH_ART + """
           ))
           and (cast(:packId as bigint) is null or c.pack_id=current_catalog_pack(:packId))
           and (cast(:yearStart as date) is null
             or (c.release_date>=:yearStart and c.release_date<:yearEnd)
             or (c.release_date is null and c.pack_id in (select pd.pack_id from catalog_pack_date pd
                    where (:game='' or pd.game_code=:game) and pd.release_date>=:yearStart and pd.release_date<:yearEnd)))
           and (:traitKey='' or c.id in (select f.card_id from catalog_search_cache f where f.game_code=:game
                and f.facets @> jsonb_build_object(cast(:traitKey as text),jsonb_build_array(cast(:traitValue as text)))))
           and (:inclusion='' or :inclusion=
        """ + ReleaseApi.INCLUSION + """
               )
           and (:ygoType='' or c.game_code='YUGIOH' and :ygoType=case
               when c.specs->>'k'='몬스터' or c.specs->>'type' ilike '%Monster' then 'MONSTER'
               when c.specs->>'k'='마법' or c.specs->>'type'='Spell Card' then 'SPELL'
               when c.specs->>'k'='함정' or c.specs->>'type'='Trap Card' then 'TRAP' end)
           and (:rarity='' or lower(c.rarity)=lower(:rarity)
             or lower(:rarity)=any(regexp_split_to_array(lower(c.rarity),'[[:space:]]+'))
             or exists (select 1 from card_variant v where v.card_id=c.id
                 and (lower(v.rarity)=lower(:rarity)
                      or lower(:rarity)=any(regexp_split_to_array(lower(v.rarity),'[[:space:]]+')))))
           and (:q='' or strpos(lower(c.effect),lower(:q))>0
               or (:lang='ko' and strpos(lower(kr_read.effect),lower(:q))>0)
               or strpos(lower(coalesce(c.specs->'texts'->>:lang,linked.texts->>:lang)),lower(:q))>0
               or c.id in (select t.card_id from card_translation t where t.lang=:lang and strpos(lower(t.effect),lower(:q))>0) or
        """ + CardEdition.MATCH_NAME + ") ";

    @Query(value=SELECT + FILTER + " order by c.id", countQuery="select count(*) from card c" + CardEdition.LEGACY_JOIN + FILTER, nativeQuery=true)
    Page<Summary> search(@Param("game") String game, @Param("packId") Long packId, @Param("lang") String lang,
                         @Param("rarity") String rarity, @Param("inclusion") String inclusion,
                         @Param("ygoType") String ygoType, @Param("q") String q,
                         @Param("yearStart") java.time.LocalDate yearStart, @Param("yearEnd") java.time.LocalDate yearEnd,
                         @Param("traitKey") String traitKey, @Param("traitValue") String traitValue,
                         @Param("withImage") boolean withImage, Pageable pageable);

    @Query(value=SELECT + " where c.status='PUBLISHED' and c.id in (:ids) and (:game='' or c.game_code=:game) order by c.id", nativeQuery=true)
    java.util.List<Summary> publishedByIds(@Param("ids") java.util.List<Long> ids,@Param("game") String game,@Param("lang") String lang);

    @Query(value=SELECT + " where c.status='PUBLISHED' and c.id=:id", nativeQuery=true)
    Optional<Summary> published(@Param("id") long id, @Param("lang") String lang);
}
