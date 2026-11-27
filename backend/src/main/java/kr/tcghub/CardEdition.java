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
            cross join lateral (select
                case when nullif(c.specs->'names'->>:lang,'') is not null
                     then coalesce(nullif(c.specs->'sources'->>:lang,''),case when c.specs->>'language'=:lang then c.source_url end)
                     when nullif(linked.names->>:lang,'') is not null then linked.source_url end as name_url,
                case when nullif(c.specs->'texts'->>:lang,'') is not null
                     then coalesce(nullif(c.specs->'sources'->>:lang,''),case when c.specs->>'language'=:lang then c.source_url end)
                     when nullif(linked.texts->>:lang,'') is not null then linked.source_url
                     when nullif(c.effect,'') is not null then coalesce(nullif(c.specs->'sources'->>(c.specs->>'language'),''),c.source_url) end
                     as effect_url) credit
            cross join lateral (select case when c.game_code='YUGIOH' and starts_with(c.legacy_key,'legacy:')
                    and c.specs->>'k' is not null then case
                when c.number ~ '-JP[0-9]+$' and c.original_name collate "C" ~ '[ぁ-ヿ一-鿿]'
                     and c.original_name collate "C" !~ '[가-힣]' then 'ja'
                when c.number ~ '-EN[0-9]+$' and c.original_name collate "C" ~ '[A-Za-z]'
                     and c.original_name collate "C" !~ '[ぁ-ヿ一-鿿가-힣]'
                     and upper(c.original_name) not in ('TBA','TBD','N/A','UNKNOWN') then 'en'
                end end as lang) original
            left join card_translation reviewed on reviewed.card_id=c.id and reviewed.lang=:lang
            cross join lateral (select
                case when reviewed.basis='PRINTED_NAME' or (requested.name is null
                     and original.lang is distinct from :lang and c.specs->>'language' is distinct from :lang)
                     then reviewed.name end as name,
                case when reviewed.basis='PRINTED_NAME' or (requested.effect is null
                     and (nullif(c.effect,'') is null or c.specs->>'language' is distinct from :lang))
                     then reviewed.effect end as effect) correction
            left join yugioh_reference_art ygo_art on c.game_code='YUGIOH'
                and ygo_art.cid=coalesce(nullif(c.specs->>'konami_id',''),linked.konami_id::text)
            cross join lateral (select 'https://artworks-ko-db.ygoresources.com'||ygo_art.ko_path as ko,
                'https://artworks-en-n.ygoresources.com'||ygo_art.en_path as en,
                'https://artworks-jp-n.ygoresources.com'||ygo_art.ja_path as ja) regional
            left join lateral (
                select v.url,v.lang,case when v.reference then 'CARD_REFERENCE' end as basis,
                       case when v.reference then v.url else c.specs->'imageSources'->>v.lang end as source,
                       case when not v.reference then c.specs->'imageProducts'->>v.lang end as product
                  from (values
                    (1,cast(:lang as text),nullif(c.specs->'images'->>:lang,''),false),
                    (2,cast(:lang as text),case :lang when 'ko' then regional.ko
                                                     when 'en' then regional.en when 'ja' then regional.ja end,true),
                    (3,c.specs->>'language',nullif(c.specs->'images'->>(c.specs->>'language'),''),false),
                    (4,'ko',regional.ko,true),(5,'en',regional.en,true),(6,'ja',regional.ja,true)
                  ) v(priority,lang,url,reference)
                 where v.url is not null order by v.priority limit 1
            ) art on true
            """;
    static final String NAME = "coalesce(correction.name,requested.name,case when original.lang=:lang then c.original_name end,requested.reference_name,c.name)";
    static final String MATCH_NAME = """
            (strpos(lower(concat_ws(' ',c.name,c.original_name,c.number,c.specs->'names'->>'ko',c.specs->'names'->>'en',
                c.specs->'names'->>'ja',linked.names->>'ko',linked.names->>'en',linked.names->>'ja',
                c.specs->'referenceNames'->>'ko',c.specs->'referenceNames'->>'en',c.specs->'referenceNames'->>'ja')),lower(:q))>0
             or c.id in (select t.card_id from card_translation t where strpos(lower(t.name),lower(:q))>0))
            """;
    static final String NAME_FIELDS = NAME + """
             as name,
            case when correction.name is not null or requested.name is not null or requested.reference_name is not null or original.lang=:lang then :lang
                 when c.specs->>'language' is not null then c.specs->>'language'
                 when c.name=c.original_name and original.lang is not null then original.lang
                 when c.legacy_key like 'legacy:%' and c.name collate "C" ~ '[가-힣]' and c.name collate "C" !~ '[ぁ-ヿ]' then 'ko'
                 else 'und' end as language,
            case when correction.name is not null then reviewed.basis
                 when requested.name is not null then case
                      when c.specs->'nameBasis'->>:lang in ('PRINTED_NAME','SOURCE_LABEL','TRANSLATED_NAME','RELATED_PRINTING')
                           then c.specs->'nameBasis'->>:lang
                      when nullif(c.specs->'names'->>:lang,'') is null and nullif(linked.names->>:lang,'') is not null then 'PRINTED_NAME'
                      when credit.name_url is not null then 'SOURCE_LABEL' end
                 when original.lang=:lang or (original.lang is not null and c.name=c.original_name) then 'IMPORTED_ORIGINAL'
                 when requested.reference_name is not null then 'RELATED_PRINTING'
                 when starts_with(c.legacy_key,'legacy:') then 'IMPORTED_LABEL'
                 when c.specs->>'language' is not null and c.source_url is not null then 'SOURCE_LABEL' end as "nameBasis",
            case when correction.name is not null then reviewed.source_url
                 when requested.name is not null then credit.name_url
                 when original.lang=:lang then null
                 when requested.reference_name is not null then c.specs->'referenceNameUrls'->>:lang
                 when c.specs->>'language' is not null then coalesce(nullif(c.specs->'sources'->>(c.specs->>'language'),''),c.source_url)
                 end as "nameReferenceUrl"
            """;
    static final String FIELDS = NAME_FIELDS + """
            ,case when correction.effect is not null then reviewed.source_url else credit.effect_url end as "effectReferenceUrl",
            case when correction.effect is not null then case when reviewed.basis='PRINTED_NAME'
                      then 'REVIEWED_PRINTING' else 'REVIEWED_TRANSLATION' end
                 when c.game_code='ONEPIECE' and c.specs->'nameBasis'->>
                      (case when requested.effect is not null then :lang else c.specs->>'language' end)='RELATED_PRINTING'
                      and coalesce(requested.effect,nullif(c.effect,'')) is not null then 'RELATED_PRINTING' end as "effectBasis",
            coalesce(correction.effect,requested.effect,c.effect) as effect,
            case when correction.effect is not null or requested.effect is not null then :lang
                 when nullif(c.effect,'') is null then null
                 when c.specs->>'language' is not null then c.specs->>'language'
                 when c.legacy_key like 'legacy:%' and c.specs->>'ej' in ('1','true') then 'ja'
                 when c.legacy_key like 'legacy:%' and c.effect collate "C" ~ '[가-힣]' and c.effect collate "C" !~ '[ぁ-ヿ]' then 'ko'
                 else 'und' end as "effectLanguage",
            art.url as "imageUrl", art.lang as "imageLanguage",art.basis as "imageBasis",
            c.specs->>'productCode' as "productCode", art.product as "imageProduct", art.source as "imageSource"
            """;
}
