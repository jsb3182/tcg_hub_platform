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
                case when c.game_code='POKEMON' then nullif(c.specs->'referenceNames'->>:lang,'') end as reference_name,
                coalesce(nullif(c.specs->'texts'->>:lang,''),nullif(linked.texts->>:lang,'')) as effect) requested
            cross join lateral (select case when c.game_code='YUGIOH' and starts_with(c.legacy_key,'legacy:')
                    and c.specs->>'k' is not null then case
                when c.number ~ '-JP[0-9]+$' and c.original_name collate "C" ~ '[ぁ-ヿ一-鿿]'
                     and c.original_name collate "C" !~ '[가-힣]' then 'ja'
                when c.number ~ '-EN[0-9]+$' and c.original_name collate "C" ~ '[A-Za-z]'
                     and c.original_name collate "C" !~ '[ぁ-ヿ一-鿿가-힣]'
                     and upper(c.original_name) not in ('TBA','TBD','N/A','UNKNOWN') then 'en'
                end end as lang) original
            cross join lateral (select case
                when nullif(c.specs->'images'->>:lang,'') is not null then :lang
                when nullif(c.specs->'images'->>(c.specs->>'language'),'') is not null then c.specs->>'language'
                end as lang) art
            """;
    static final String NAME = "coalesce(requested.name,case when original.lang=:lang then c.original_name end,requested.reference_name,c.name)";
    static final String FIELDS = NAME + """
             as name,
            case when requested.name is not null or requested.reference_name is not null or original.lang=:lang then :lang
                 when c.specs->>'language' is not null then c.specs->>'language'
                 when c.name=c.original_name and original.lang is not null then original.lang
                 when c.legacy_key like 'legacy:%' and c.name collate "C" ~ '[가-힣]' and c.name collate "C" !~ '[ぁ-ヿ]' then 'ko'
                 else 'und' end as language,
            case when requested.name is not null then null
                 when original.lang=:lang or (original.lang is not null and c.name=c.original_name) then 'IMPORTED_ORIGINAL'
                 when requested.reference_name is not null then 'RELATED_PRINTING'
                 when starts_with(c.legacy_key,'legacy:') then 'IMPORTED_LABEL' end as "nameBasis",
            case when requested.name is null and requested.reference_name is not null
                 then c.specs->'referenceNameUrls'->>:lang end as "nameReferenceUrl",
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
