package kr.tcghub;

/** Resolve each field independently; an available name does not imply translated rules or artwork. */
final class CardEdition {
    private CardEdition() {}
    static final String LEGACY_JOIN = """
             left join legacy_card_edition linked on linked.card_id=c.id
                 and linked.matched_number=c.number and linked.matched_name=c.original_name
            """;
    static final String JOIN = LEGACY_JOIN + """
            cross join lateral (select
                coalesce(nullif(c.specs->'names'->>:lang,''),nullif(linked.names->>:lang,'')) as name,
                coalesce(nullif(c.specs->'texts'->>:lang,''),nullif(linked.texts->>:lang,'')) as effect) requested
            cross join lateral (select case
                when nullif(c.specs->'images'->>:lang,'') is not null then :lang
                when nullif(c.specs->'images'->>(c.specs->>'language'),'') is not null then c.specs->>'language'
                end as lang) art
            """;
    static final String FIELDS = """
            coalesce(requested.name,c.name) as name,
            case when requested.name is not null then :lang
                 when c.specs->>'language' is not null then c.specs->>'language'
                 when c.legacy_key like 'legacy:%' and c.name collate "C" ~ '[가-힣]' and c.name collate "C" !~ '[ぁ-ヿ]' then 'ko'
                 else 'und' end as language,
            coalesce(requested.effect,c.effect) as effect,
            case when requested.effect is not null then :lang
                 when nullif(c.effect,'') is null then null
                 when c.specs->>'language' is not null then c.specs->>'language'
                 when c.legacy_key like 'legacy:%' and c.specs->>'ej' in ('1','true') then 'ja'
                 when c.legacy_key like 'legacy:%' and c.effect collate "C" ~ '[가-힣]' and c.effect collate "C" !~ '[ぁ-ヿ]' then 'ko'
                 else 'und' end as "effectLanguage",
            c.specs->'images'->>art.lang as "imageUrl", art.lang as "imageLanguage",
            c.specs->>'productCode' as "productCode", c.specs->'imageProducts'->>art.lang as "imageProduct",
            c.specs->'imageSources'->>art.lang as "imageSource"
            """;
}
