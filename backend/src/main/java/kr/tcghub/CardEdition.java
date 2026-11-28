package kr.tcghub;

/** Resolve each field independently; an available name does not imply translated rules or artwork. */
final class CardEdition {
    private CardEdition() {}
    private static final String LEGACY_EDITION = """
             left join legacy_card_edition linked on linked.card_id=c.id
                 and linked.matched_number=c.number and linked.matched_name=c.original_name
            """;
    static final String LEGACY_JOIN = LEGACY_EDITION + """
             left join wiki_card_document wiki on wiki.game_code=c.game_code and wiki.lookup_key=
                 case when c.game_code='YUGIOH' and starts_with(c.legacy_key,'catalog:YUGIOH:')
                      then 'cid:'||(c.specs->>'konami_id')
                      when c.game_code='YUGIOH' and starts_with(c.legacy_key,'legacy:')
                      then 'cid:'||linked.konami_id::text else c.legacy_key end
                 and (wiki.printing_number is null or wiki.printing_number=c.number)
                 and (wiki.passcode is null or c.specs->>'passcode' is null or wiki.passcode=c.specs->>'passcode')
             left join card_korean_reading kr_read on kr_read.card_id=c.id and kr_read.due_at is null
            """;
    private static final String REGIONAL_ART = """
            left join yugioh_reference_art ygo_art on c.game_code='YUGIOH'
                and ygo_art.cid=coalesce(nullif(c.specs->>'konami_id',''),linked.konami_id::text)
            """;
    private static final String ART_EDITIONS = """
            (values ('ko',c.specs->'images'->>'ko',false),('en',c.specs->'images'->>'en',false),
                    ('ja',c.specs->'images'->>'ja',false),
                    ('ko','https://artworks-ko-db.ygoresources.com'||ygo_art.ko_path,true),
                    ('en','https://artworks-en-n.ygoresources.com'||ygo_art.en_path,true),
                    ('ja','https://artworks-jp-n.ygoresources.com'||ygo_art.ja_path,true)) v(lang,url,reference)
            """;
    // Start with cached files: an approved URL or a Neuron-only variant is not a catalog thumbnail.
    static final String CARDS_WITH_ART = """
            select a.card_id from catalog_art_file f join catalog_art_card a on a.file_id=f.id
            join card c on c.id=a.card_id
            """ + LEGACY_EDITION + REGIONAL_ART + """
            where f.storage_key is not null and f.source_url in (select v.url from
            """ + ART_EDITIONS + ") ";
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
            left join lateral (
                select case when count(distinct s.name)=1 then min(s.name) end as name,
                       case when count(distinct s.effect)=1 then min(s.effect) end as effect,
                       min(s.source_url) as name_url,min(s.source_url) filter(where s.effect is not null) as effect_url,
                       bool_and(s.provider='YUGIOHKR') filter(where s.effect is not null) as related
                from supplemental_printing s where s.card_id=c.id and s.lang=:lang and s.provider<>'RIFTCODEX'
            ) supplement on c.specs->>'language' is distinct from :lang or nullif(c.effect,'') is null
            cross join lateral (select case when :lang='ko'
                 and c.specs->>'language' is distinct from 'ko'
                 and not (coalesce(starts_with(c.legacy_key,'legacy:'),false) and c.name collate "C" ~ '[가-힣]'
                          and c.name collate "C" !~ '[ぁ-ヿ]')
                 then nullif(wiki.names->>'ko','') end as name,
                 case when :lang='ko' and c.specs->>'language' is distinct from 'ko'
                      and not (starts_with(coalesce(c.legacy_key,''),'legacy:') and coalesce(c.effect,'') collate "C" ~ '[가-힣]'
                               and c.effect collate "C" !~ '[ぁ-ヿ]') then wiki.korean_text end as effect) wiki_label
            cross join lateral (select
                case when reviewed.basis='PRINTED_NAME' or (requested.name is null
                     and original.lang is distinct from :lang and c.specs->>'language' is distinct from :lang)
                     then reviewed.name end as name,
                case when reviewed.basis='PRINTED_NAME' or (requested.effect is null
                     and (nullif(c.effect,'') is null or c.specs->>'language' is distinct from :lang))
                     then reviewed.effect end as effect) correction
            """ + REGIONAL_ART + """
            left join lateral (
                select '/media/'||f.storage_key as url,v.lang,case when v.reference then 'CARD_REFERENCE' end as basis,
                       case when v.reference then v.url else c.specs->'imageSources'->>v.lang end as source,
                       case when not v.reference then c.specs->'imageProducts'->>v.lang end as product
                  from
            """ + ART_EDITIONS + """
                  join catalog_art_file f on f.source_url=v.url and f.storage_key is not null
                  join catalog_art_card allowed on allowed.file_id=f.id and allowed.card_id=c.id
                 order by case when v.lang=:lang and not v.reference then 1 when v.lang=:lang then 2
                               when not v.reference and v.lang=c.specs->>'language' then 3
                               when not v.reference then 4 else 5 end,
                          case v.lang when 'ko' then 1 when 'en' then 2 else 3 end limit 1
            ) art on true
            """;
    static final String NAME = "coalesce(correction.name,requested.name,case when original.lang=:lang then c.original_name end,requested.reference_name,wiki_label.name,case when c.specs->>'language' is distinct from :lang then supplement.name end,case when :lang='ko' then kr_read.name end,c.name)";
    static final String MATCH_NAME = """
            (strpos(lower(concat_ws(' ',c.name,c.original_name,c.number,c.specs->'names'->>'ko',c.specs->'names'->>'en',
                c.specs->'names'->>'ja',linked.names->>'ko',linked.names->>'en',linked.names->>'ja',
                c.specs->'referenceNames'->>'ko',c.specs->'referenceNames'->>'en',c.specs->'referenceNames'->>'ja',wiki.names->>'ko',kr_read.name)),lower(:q))>0
             or c.id in (select t.card_id from card_translation t where strpos(lower(t.name),lower(:q))>0))
            """;
    static final String NAME_FIELDS = NAME + """
             as name,
            case when correction.name is not null or requested.name is not null or requested.reference_name is not null or original.lang=:lang or wiki_label.name is not null
                     or supplement.name is not null or (:lang='ko' and kr_read.name is not null) then :lang
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
                 when original.lang=:lang then 'IMPORTED_ORIGINAL'
                 when requested.reference_name is not null then 'RELATED_PRINTING'
                 when wiki_label.name is not null then 'WIKI_REFERENCE'
                 when supplement.name is not null and c.specs->>'language' is distinct from :lang then 'SOURCE_LABEL'
                 when :lang='ko' and kr_read.name is not null then kr_read.basis
                 when original.lang is not null and c.name=c.original_name then 'IMPORTED_ORIGINAL'
                 when starts_with(c.legacy_key,'legacy:') then 'IMPORTED_LABEL'
                 when c.specs->>'language' is not null and c.source_url is not null then 'SOURCE_LABEL' end as "nameBasis",
            case when correction.name is not null then reviewed.source_url
                 when requested.name is not null then credit.name_url
                 when original.lang=:lang then null
                 when requested.reference_name is not null then c.specs->'referenceNameUrls'->>:lang
                 when wiki_label.name is not null then wiki.document_url
                 when supplement.name is not null and c.specs->>'language' is distinct from :lang then supplement.name_url
                 when :lang='ko' and kr_read.name is not null then c.source_url
                 when c.specs->>'language' is not null then coalesce(nullif(c.specs->'sources'->>(c.specs->>'language'),''),c.source_url)
                 end as "nameReferenceUrl"
            """;
    static final String FIELDS = NAME_FIELDS + """
            ,case when correction.effect is not null then reviewed.source_url
                  when requested.effect is null and wiki_label.effect is not null then wiki.document_url
                  when requested.effect is null and supplement.effect is not null then supplement.effect_url
                  when requested.effect is null and :lang='ko' and kr_read.effect is not null then c.source_url else credit.effect_url end as "effectReferenceUrl",
            case when correction.effect is not null then case when reviewed.basis='PRINTED_NAME'
                      then 'REVIEWED_PRINTING' else 'REVIEWED_TRANSLATION' end
                 when requested.effect is null and wiki_label.effect is not null then 'NAMUWIKI_KO'
                 when requested.effect is null and supplement.effect is not null then case when supplement.related
                       then 'RELATED_PRINTING' else 'SOURCE_LABEL' end
                 when requested.effect is null and :lang='ko' and kr_read.effect is not null then kr_read.basis
                 when c.game_code='ONEPIECE' and c.specs->'nameBasis'->>
                      (case when requested.effect is not null then :lang else c.specs->>'language' end)='RELATED_PRINTING'
                      and coalesce(requested.effect,nullif(c.effect,'')) is not null then 'RELATED_PRINTING' end as "effectBasis",
            coalesce(correction.effect,requested.effect,wiki_label.effect,supplement.effect,case when :lang='ko' then kr_read.effect end,c.effect) as effect,
            case when correction.effect is not null or requested.effect is not null or wiki_label.effect is not null or supplement.effect is not null or (:lang='ko' and kr_read.effect is not null) then :lang
                 when nullif(c.effect,'') is null then null
                 when c.specs->>'language' is not null then c.specs->>'language'
                 when c.legacy_key like 'legacy:%' and c.specs->>'ej' in ('1','true') then 'ja'
                 when c.legacy_key like 'legacy:%' and c.effect collate "C" ~ '[가-힣]' and c.effect collate "C" !~ '[ぁ-ヿ]' then 'ko'
                 else 'und' end as "effectLanguage",
            art.url as "imageUrl", art.lang as "imageLanguage",art.basis as "imageBasis",
            c.specs->>'productCode' as "productCode", art.product as "imageProduct", art.source as "imageSource"
            """;
}
