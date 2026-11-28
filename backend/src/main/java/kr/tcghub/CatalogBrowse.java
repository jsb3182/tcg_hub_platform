package kr.tcghub;

import java.time.LocalDate;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Component;

/** Select a page of printing IDs before joining its rules, translations and artwork. */
@Component
class CatalogBrowse {
    record Filter(String game, Long packId, String lang, String rarity, String inclusion, String ygoType,
                  String text, LocalDate start, String traitKey, String traitValue, boolean withImage, boolean koreanFirst) {}
    record Page(List<Long> ids, long total) {}

    private final JdbcClient db;
    CatalogBrowse(JdbcClient db) { this.db=db; }

    Page page(Filter f, int page, int size) {
        Map<String,Object> args=new HashMap<>();
        var conditions=new ArrayList<String>();
        String from=" from catalog_search_cache b ";
        boolean needsCard=f.packId()!=null || !f.rarity().isEmpty() || !f.inclusion().isEmpty() ||
                !f.ygoType().isEmpty() || !f.text().isEmpty() || f.start()!=null;
        if (needsCard) from+=" join card c on c.id=b.card_id ";
        if (!f.text().isEmpty()) {
            from+=CardEdition.LEGACY_JOIN;
            conditions.add("""
                    (strpos(lower(c.effect),lower(:q))>0
                    or (:lang='ko' and strpos(lower(kr_read.effect),lower(:q))>0)
                    or strpos(lower(coalesce(c.specs->'texts'->>:lang,linked.texts->>:lang)),lower(:q))>0
                    or exists(select from card_translation t where t.card_id=c.id and t.lang=:lang and strpos(lower(t.effect),lower(:q))>0)
                    or """+" "+CardEdition.MATCH_NAME+")");
            args.put("q",f.text());
            args.put("lang",f.lang());
        }
        if (!f.game().isEmpty()) { conditions.add("b.game_code=:game"); args.put("game",f.game()); }
        if (f.packId()!=null) { conditions.add("c.pack_id=current_catalog_pack(:pack)"); args.put("pack",f.packId()); }
        if (f.start()!=null) {
            conditions.add("""
                    ((c.release_date>=:start and c.release_date<:endDate) or (c.release_date is null and exists (
                    select from catalog_pack_date pd where pd.pack_id=c.pack_id and pd.release_date>=:start and pd.release_date<:endDate)))
                    """);
            args.put("start",f.start()); args.put("endDate",f.start().plusYears(1));
        }
        if (!f.traitKey().isEmpty()) {
            conditions.add("b.facets @> jsonb_build_object(cast(:trait as text),jsonb_build_array(cast(:value as text)))");
            args.put("trait",f.traitKey()); args.put("value",f.traitValue());
        }
        if (!f.inclusion().isEmpty()) { conditions.add(":inclusion=("+ReleaseApi.INCLUSION+")"); args.put("inclusion",f.inclusion()); }
        if (!f.ygoType().isEmpty()) {
            conditions.add("""
                    c.game_code='YUGIOH' and :ygoType=case
                    when c.specs->>'k'='몬스터' or c.specs->>'type' ilike '%Monster' then 'MONSTER'
                    when c.specs->>'k'='마법' or c.specs->>'type'='Spell Card' then 'SPELL'
                    when c.specs->>'k'='함정' or c.specs->>'type'='Trap Card' then 'TRAP' end
                    """);
            args.put("ygoType",f.ygoType());
        }
        if (!f.rarity().isEmpty()) {
            conditions.add("""
                    (lower(c.rarity)=lower(:rarity) or lower(:rarity)=any(regexp_split_to_array(lower(c.rarity),'[[:space:]]+'))
                    or exists(select from card_variant v where v.card_id=c.id and (lower(v.rarity)=lower(:rarity)
                    or lower(:rarity)=any(regexp_split_to_array(lower(v.rarity),'[[:space:]]+')))))
                    """);
            args.put("rarity",f.rarity());
        }
        String where=conditions.isEmpty() ? "" : " where "+String.join(" and ",conditions);
        String photos="(select p.card_id,bit_or(p.mask) as mask from catalog_browse_photo p "+
                (f.game().isEmpty() ? "" : "join catalog_search_cache scope on scope.card_id=p.card_id and scope.game_code=:game ")+
                "group by p.card_id) photo on photo.card_id=b.card_id ";
        if (f.withImage()) from+=" join "+photos;
        String ordering="b.card_id";
        String rankedFrom=from;
        if (f.koreanFirst()) {
            if (!f.withImage()) rankedFrom+=" left join "+photos;
            rankedFrom+=" left join card_translation korean on korean.card_id=b.card_id and korean.lang='ko' "+
                    "left join card_korean_reading reading on reading.card_id=b.card_id and reading.due_at is null ";
            ordering="""
                    case when (photo.mask & 2)<>0 then 0
                         when b.korean_title or korean.name is not null or reading.name is not null then 1
                         when photo.mask is not null then 2 else 3 end,b.card_id
                    """;
        }
        args.put("take",size); args.put("offset",(long)page*size);
        var ids=db.sql("select b.card_id"+rankedFrom+where+" order by "+ordering+" limit :take offset :offset")
                .params(args).query(Long.class).list();
        long total=ids.size()<size && (page==0 || !ids.isEmpty()) ? (long)page*size+ids.size() :
                db.sql("select count(*)"+from+where).params(args).query(Long.class).single();
        return new Page(ids,total);
    }
}
