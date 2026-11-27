-- A local export projection. Each translated field carries its own source classification.
CREATE VIEW catalog_localized_printing AS
SELECT c.id AS card_id,c.game_code AS game_type,c.pack_id,c.number,c.rarity,c.release_date,
       labels.names->>'ko' AS name_ko,labels.names->>'en' AS name_en,labels.names->>'ja' AS name_ja,
       labels.texts->>'ko' AS text_ko,labels.texts->>'en' AS text_en,labels.texts->>'ja' AS text_ja,
       labels.origins AS translation_source,w.document_url AS namuwiki_url,art.local_image_path
FROM card c
LEFT JOIN legacy_card_edition l ON l.card_id=c.id AND l.matched_number=c.number AND l.matched_name=c.original_name
LEFT JOIN wiki_card_document w ON w.game_code=c.game_code AND w.lookup_key=CASE WHEN c.game_code='YUGIOH'
    THEN 'cid:'||coalesce(c.specs->>'konami_id',l.konami_id::text) ELSE c.legacy_key END
    AND (w.printing_number IS NULL OR w.printing_number=c.number)
    AND (w.passcode IS NULL OR c.specs->>'passcode' IS NULL OR w.passcode=c.specs->>'passcode')
LEFT JOIN card_korean_reading k ON k.card_id=c.id AND k.due_at IS NULL
CROSS JOIN LATERAL (
    SELECT jsonb_object_agg(language.code,chosen.name) AS names,jsonb_object_agg(language.code,chosen.effect) AS texts,
           jsonb_object_agg(language.code,jsonb_strip_nulls(jsonb_build_object('name',chosen.name_basis,'text',chosen.effect_basis))) AS origins
    FROM (VALUES ('ko'),('en'),('ja')) language(code)
    LEFT JOIN card_translation t ON t.card_id=c.id AND t.lang=language.code
    CROSS JOIN LATERAL (
        SELECT coalesce(nullif(c.specs->'names'->>language.code,''),nullif(l.names->>language.code,''),
                    CASE WHEN c.specs->>'language'=language.code THEN c.name
                         WHEN language.code='ko' AND starts_with(c.legacy_key,'legacy:') AND c.name ~ '[가-힣]' AND c.name !~ '[ぁ-ヿ]' THEN c.name END) AS name,
               coalesce(nullif(c.specs->'texts'->>language.code,''),nullif(l.texts->>language.code,''),
                    CASE WHEN c.specs->>'language'=language.code THEN nullif(c.effect,'')
                         WHEN language.code='ko' AND starts_with(c.legacy_key,'legacy:') AND c.effect ~ '[가-힣]' AND c.effect !~ '[ぁ-ヿ]' THEN c.effect END) AS effect,
               coalesce(c.specs->'sources'->>language.code,l.source_url,c.source_url) AS url
    ) source
    CROSS JOIN LATERAL (
        SELECT CASE WHEN language.code='ko' AND source.url ~ '^https?://(www\.)?(db\.yugioh-card\.com|pokemoncard\.co\.kr|onepiece-cardgame\.kr|nivelarena\.co\.kr|playriftbound\.com|riftbound\.leagueoflegends\.com)/'
                         THEN 'OFFICIAL_KO' ELSE 'SOURCE_LABEL' END AS origin
    ) credit
    LEFT JOIN LATERAL (
        SELECT CASE WHEN count(DISTINCT s.name)=1 THEN min(s.name) END AS name,
               CASE WHEN count(DISTINCT s.effect)=1 THEN min(s.effect) END AS effect
        FROM supplemental_printing s WHERE s.card_id=c.id AND s.lang=language.code AND s.provider<>'RIFTCODEX'
    ) supplement ON true
    CROSS JOIN LATERAL (
        SELECT (array_agg(v.name ORDER BY priority) FILTER(WHERE v.name IS NOT NULL))[1] AS name,
               (array_agg(v.effect ORDER BY priority) FILTER(WHERE v.effect IS NOT NULL))[1] AS effect,
               (array_agg(basis ORDER BY priority) FILTER(WHERE v.name IS NOT NULL))[1] AS name_basis,
               (array_agg(basis ORDER BY priority) FILTER(WHERE v.effect IS NOT NULL))[1] AS effect_basis
        FROM (VALUES
             (1,CASE WHEN t.basis='PRINTED_NAME' THEN t.name END,CASE WHEN t.basis='PRINTED_NAME' THEN t.effect END,'REVIEWED_PRINTING'),
             (2,source.name,source.effect,credit.origin),(3,t.name,t.effect,'REVIEWED_TRANSLATION'),
             (4,CASE WHEN language.code='ko' THEN w.names->>'ko' END,CASE WHEN language.code='ko' THEN w.korean_text END,'NAMUWIKI_KO'),
             (5,supplement.name,supplement.effect,'SOURCE_LABEL'),
             (6,CASE WHEN language.code='ko' THEN k.name END,CASE WHEN language.code='ko' THEN k.effect END,k.basis)
        ) v(priority,name,effect,basis)
    ) chosen
) labels
LEFT JOIN LATERAL (
    SELECT '/media/'||f.storage_key AS local_image_path FROM catalog_art_card a JOIN catalog_art_file f ON f.id=a.file_id
    WHERE a.card_id=c.id AND f.storage_key IS NOT NULL ORDER BY f.id LIMIT 1
) art ON true
WHERE c.status='PUBLISHED';
