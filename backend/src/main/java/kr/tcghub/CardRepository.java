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
        java.time.LocalDate getReleaseDate();
    }
    String SELECT = """
        select c.id, c.game_code as "gameCode", c.pack_id as "packId", p.name as "packName",
               c.name, c.original_name as "originalName", c.number, c.rarity, c.effect,
               c.release_date as "releaseDate" from card c left join pack p on p.id=c.pack_id
        """;
    String FILTER = """
         where c.status='PUBLISHED' and (:game='' or c.game_code=:game)
           and (cast(:packId as bigint) is null or c.pack_id=:packId)
           and (:rarity='' or :rarity=any(regexp_split_to_array(c.rarity,'[[:space:]]+'))
             or exists (select 1 from card_variant v where v.card_id=c.id
                 and :rarity=any(regexp_split_to_array(v.rarity,'[[:space:]]+'))))
           and (:q='' or strpos(lower(concat_ws(' ',c.name,c.original_name,c.number,c.effect)),lower(:q))>0)
        """;

    @Query(value=SELECT + FILTER + " order by c.id", countQuery="select count(*) from card c" + FILTER, nativeQuery=true)
    Page<Summary> search(@Param("game") String game, @Param("packId") Long packId,
                         @Param("rarity") String rarity, @Param("q") String q, Pageable pageable);

    @Query(value=SELECT + " where c.status='PUBLISHED' and c.id=:id", nativeQuery=true)
    Optional<Summary> published(@Param("id") long id);
}
