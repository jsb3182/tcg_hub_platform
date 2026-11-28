-- A grant can also be a capture-only image. Classify its displayable editions once
-- when the grant or its identity changes. Download status is always read live.
ALTER TABLE catalog_art_card ADD COLUMN edition_mask smallint NOT NULL DEFAULT 0;

CREATE VIEW catalog_expected_face AS
SELECT c.id AS card_id, edition.url, bit_or(edition.bits)::smallint AS mask
FROM card c
LEFT JOIN legacy_card_edition e ON e.card_id=c.id AND e.matched_number=c.number AND e.matched_name=c.original_name
LEFT JOIN yugioh_reference_art y ON c.game_code='YUGIOH'
    AND y.cid=coalesce(nullif(c.specs->>'konami_id',''),e.konami_id::text)
CROSS JOIN LATERAL (VALUES
    (2,c.specs#>>'{images,ko}'),(4,c.specs#>>'{images,en}'),(8,c.specs#>>'{images,ja}'),
    (2,CASE WHEN c.game_code='NIVEL' THEN c.specs->>'nivelThumbnail' END),
    (2,'https://artworks-ko-db.ygoresources.com'||y.ko_path),
    (4,'https://artworks-en-n.ygoresources.com'||y.en_path),
    (8,'https://artworks-jp-n.ygoresources.com'||y.ja_path)) edition(bits,url)
WHERE c.status='PUBLISHED' AND edition.url IS NOT NULL
    AND NOT starts_with(edition.url,'https://images.ygoprodeck.com/')
GROUP BY c.id,edition.url;

UPDATE catalog_art_card a SET edition_mask=e.mask
FROM catalog_expected_face e JOIN catalog_art_file f ON f.source_url=e.url
WHERE a.card_id=e.card_id AND a.file_id=f.id;

CREATE FUNCTION classify_catalog_grant() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    -- Serialize grants against edits to their card identity.
    PERFORM FROM card WHERE id=NEW.card_id FOR SHARE;
    SELECT coalesce((SELECT mask FROM catalog_expected_face e JOIN catalog_art_file f ON f.source_url=e.url
                     WHERE f.id=NEW.file_id AND e.card_id=NEW.card_id),0) INTO NEW.edition_mask;
    RETURN NEW;
END $$;
CREATE TRIGGER classify_catalog_grant BEFORE INSERT OR UPDATE OF card_id,file_id ON catalog_art_card
FOR EACH ROW EXECUTE FUNCTION classify_catalog_grant();

CREATE FUNCTION reclassify_catalog_grants(target bigint) RETURNS void LANGUAGE sql AS $$
    UPDATE catalog_art_card a SET edition_mask=coalesce(e.mask,0)
    FROM catalog_art_file f LEFT JOIN catalog_expected_face e ON e.card_id=target AND e.url=f.source_url
    WHERE a.card_id=target AND a.file_id=f.id AND a.edition_mask<>coalesce(e.mask,0)
$$;
CREATE FUNCTION reclassify_card_grants() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_TABLE_NAME='card' THEN
        PERFORM reclassify_catalog_grants(NEW.id);
    ELSE
        IF TG_OP<>'INSERT' THEN PERFORM reclassify_catalog_grants(OLD.card_id); END IF;
        IF TG_OP='INSERT' OR (TG_OP='UPDATE' AND NEW.card_id<>OLD.card_id) THEN
            PERFORM reclassify_catalog_grants(NEW.card_id);
        END IF;
    END IF;
    RETURN NULL;
END $$;
CREATE TRIGGER reclassify_card_grants AFTER UPDATE OF specs,status,game_code,number,original_name ON card
FOR EACH ROW WHEN ((OLD.specs->'images',OLD.specs->>'nivelThumbnail',OLD.specs->>'konami_id',OLD.status,OLD.game_code,OLD.number,OLD.original_name)
    IS DISTINCT FROM (NEW.specs->'images',NEW.specs->>'nivelThumbnail',NEW.specs->>'konami_id',NEW.status,NEW.game_code,NEW.number,NEW.original_name))
EXECUTE FUNCTION reclassify_card_grants();
CREATE TRIGGER reclassify_legacy_grants AFTER INSERT OR UPDATE OR DELETE ON legacy_card_edition
FOR EACH ROW EXECUTE FUNCTION reclassify_card_grants();
CREATE FUNCTION reclassify_manifest_grants() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE ids text[];
BEGIN
    ids:=CASE TG_OP WHEN 'DELETE' THEN ARRAY[OLD.cid] WHEN 'INSERT' THEN ARRAY[NEW.cid] ELSE ARRAY[OLD.cid,NEW.cid] END;
    PERFORM reclassify_catalog_grants(c.id) FROM card c LEFT JOIN legacy_card_edition e ON e.card_id=c.id
      WHERE c.game_code='YUGIOH' AND coalesce(nullif(c.specs->>'konami_id',''),e.konami_id::text)=ANY(ids)
        AND EXISTS(SELECT FROM catalog_art_card a WHERE a.card_id=c.id);
    RETURN NULL;
END $$;
CREATE TRIGGER reclassify_manifest_grants AFTER INSERT OR UPDATE OR DELETE ON yugioh_reference_art
FOR EACH ROW EXECUTE FUNCTION reclassify_manifest_grants();
CREATE FUNCTION reclassify_file_grants() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    PERFORM reclassify_catalog_grants(a.card_id) FROM catalog_art_card a WHERE a.file_id=NEW.id;
    RETURN NULL;
END $$;
CREATE TRIGGER reclassify_file_grants AFTER UPDATE OF source_url ON catalog_art_file
FOR EACH ROW WHEN (NEW.source_url IS DISTINCT FROM OLD.source_url) EXECUTE FUNCTION reclassify_file_grants();

-- Every tile is delivered in one HTTP response. The public listings and the media
-- route must agree when even one of a sheet's cards is pending or withdrawn.
CREATE VIEW public_catalog_sheet AS
SELECT s.* FROM image_sheet s WHERE NOT s.retired AND NOT EXISTS (
    SELECT FROM card_variant v JOIN card peer ON peer.id=v.card_id WHERE v.sheet_id=s.id AND peer.status<>'PUBLISHED');

-- Keep successful downloads immediately visible, including reviewed YGOPRODeck faces
-- only while their live printing, source hash and eligibility still match.
CREATE VIEW catalog_browse_photo AS
SELECT a.card_id,a.edition_mask AS mask FROM catalog_art_card a JOIN catalog_art_file f ON f.id=a.file_id
WHERE a.edition_mask<>0 AND f.storage_key IS NOT NULL
UNION ALL
SELECT r.card_id,CASE r.language WHEN 'ko' THEN 2 WHEN 'en' THEN 4 ELSE 8 END
FROM catalog_ygo_provider_reference r JOIN catalog_art_file f ON f.source_url=r.source_url AND f.source_sha256=r.source_sha256
JOIN catalog_art_card a ON a.file_id=f.id AND a.card_id=r.card_id WHERE f.storage_key IS NOT NULL
UNION ALL
SELECT v.card_id,CASE e.language WHEN 'ko' THEN 2 WHEN 'en' THEN 4 WHEN 'ja' THEN 8 ELSE 1 END
FROM card_variant v JOIN public_catalog_sheet s ON s.id=v.sheet_id
LEFT JOIN verified_atlas_edition e ON e.storage_key=s.storage_key AND e.col_idx=v.col_idx AND e.row_idx=v.row_idx;

-- The thumbnail survives the first switch to an official Nivel full-size URL.
-- Every other changed identity still revokes the grant exactly as before.
CREATE OR REPLACE FUNCTION clear_catalog_art_card() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.status='PUBLISHED' AND (OLD.status,OLD.game_code,OLD.legacy_key,OLD.number,OLD.original_name,OLD.specs->>'konami_id')
       IS NOT DISTINCT FROM (NEW.status,NEW.game_code,NEW.legacy_key,NEW.number,NEW.original_name,NEW.specs->>'konami_id') THEN
        DELETE FROM catalog_art_card a USING catalog_art_file f WHERE a.card_id=OLD.id AND a.file_id=f.id
        AND NOT EXISTS (SELECT FROM (VALUES ('ko'),('en'),('ja')) l(lang)
                  WHERE f.source_url=OLD.specs->'images'->>l.lang AND f.source_url=NEW.specs->'images'->>l.lang)
        AND NOT coalesce(NEW.game_code='NIVEL' AND f.source_url=NEW.specs->>'nivelThumbnail'
             AND f.source_url IN (OLD.specs#>>'{images,ko}',OLD.specs->>'nivelThumbnail'),false);
    ELSE
        DELETE FROM catalog_art_card WHERE card_id=OLD.id;
    END IF;
    RETURN NEW;
END $$;
DROP TRIGGER catalog_art_source_changed ON card;
CREATE TRIGGER catalog_art_source_changed AFTER UPDATE OF specs,status,game_code,legacy_key,number,original_name ON card
FOR EACH ROW WHEN ((OLD.specs->'images',OLD.specs->>'nivelThumbnail',OLD.specs->>'konami_id',OLD.status,OLD.game_code,OLD.legacy_key,OLD.number,OLD.original_name)
    IS DISTINCT FROM (NEW.specs->'images',NEW.specs->>'nivelThumbnail',NEW.specs->>'konami_id',NEW.status,NEW.game_code,NEW.legacy_key,NEW.number,NEW.original_name))
EXECUTE FUNCTION clear_catalog_art_card();
ANALYZE catalog_art_card;

-- The first page needs a language hint, not the full JSON rules of 93,000 cards.
ALTER TABLE catalog_search_cache ADD COLUMN korean_title boolean NOT NULL DEFAULT false;
ALTER TABLE catalog_search_cache ADD COLUMN title_wiki_key text;
CREATE VIEW catalog_title_evidence AS
SELECT c.id AS card_id,identity.wiki_key,coalesce(c.specs->>'language'='ko' OR nullif(c.specs#>>'{names,ko}','') IS NOT NULL
    OR (c.game_code='POKEMON' AND nullif(c.specs#>>'{referenceNames,ko}','') IS NOT NULL)
    OR (starts_with(c.legacy_key,'legacy:') AND c.name COLLATE "C" ~ '[가-힣]' AND c.name COLLATE "C" !~ '[ぁ-ヿ]')
    OR nullif(l.names->>'ko','') IS NOT NULL OR nullif(w.names->>'ko','') IS NOT NULL
    OR (SELECT count(DISTINCT s.name)=1 FROM supplemental_printing s
        WHERE s.card_id=c.id AND s.lang='ko' AND s.provider<>'RIFTCODEX'),false) AS known
FROM card c LEFT JOIN legacy_card_edition l ON l.card_id=c.id AND l.matched_number=c.number AND l.matched_name=c.original_name
CROSS JOIN LATERAL (SELECT CASE
    WHEN c.game_code='YUGIOH' AND starts_with(c.legacy_key,'catalog:YUGIOH:') THEN 'cid:'||(c.specs->>'konami_id')
    WHEN c.game_code='YUGIOH' AND starts_with(c.legacy_key,'legacy:') THEN 'cid:'||l.konami_id::text
    ELSE c.legacy_key END AS wiki_key) identity
LEFT JOIN wiki_card_document w ON w.game_code=c.game_code AND w.lookup_key=identity.wiki_key
    AND (w.printing_number IS NULL OR w.printing_number=c.number)
    AND (w.passcode IS NULL OR c.specs->>'passcode' IS NULL OR w.passcode=c.specs->>'passcode')
WHERE c.status='PUBLISHED';
UPDATE catalog_search_cache b SET korean_title=e.known,title_wiki_key=e.wiki_key FROM catalog_title_evidence e
WHERE b.card_id=e.card_id AND (b.korean_title,b.title_wiki_key) IS DISTINCT FROM (e.known,e.wiki_key);
CREATE INDEX catalog_title_wiki_lookup ON catalog_search_cache(game_code,title_wiki_key) WHERE title_wiki_key IS NOT NULL;
CREATE FUNCTION refresh_catalog_title_hint(target bigint) RETURNS void LANGUAGE plpgsql AS $$
BEGIN
    PERFORM FROM catalog_search_cache WHERE card_id=target FOR UPDATE;
    UPDATE catalog_search_cache b SET korean_title=e.known,title_wiki_key=e.wiki_key FROM catalog_title_evidence e
    WHERE b.card_id=target AND e.card_id=target AND (b.korean_title,b.title_wiki_key) IS DISTINCT FROM (e.known,e.wiki_key);
END $$;
CREATE FUNCTION update_catalog_title_hint() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_TABLE_NAME='card' THEN
        IF NEW.status='PUBLISHED' THEN PERFORM refresh_catalog_title_hint(NEW.id); END IF;
    ELSE
        IF TG_OP<>'INSERT' THEN PERFORM refresh_catalog_title_hint(OLD.card_id); END IF;
        IF TG_OP='INSERT' OR (TG_OP='UPDATE' AND NEW.card_id IS DISTINCT FROM OLD.card_id) THEN
            PERFORM refresh_catalog_title_hint(NEW.card_id);
        END IF;
    END IF;
    RETURN NULL;
END $$;
-- Run after catalog_search_changed creates its row on insert or publication.
CREATE TRIGGER catalog_title_hint AFTER INSERT OR UPDATE OF name,specs,status,legacy_key,number,original_name,game_code ON card
FOR EACH ROW EXECUTE FUNCTION update_catalog_title_hint();
CREATE TRIGGER catalog_title_legacy AFTER INSERT OR UPDATE OR DELETE ON legacy_card_edition
FOR EACH ROW EXECUTE FUNCTION update_catalog_title_hint();
CREATE TRIGGER catalog_title_supplement AFTER INSERT OR UPDATE OF card_id,name,lang,provider OR DELETE ON supplemental_printing
FOR EACH ROW EXECUTE FUNCTION update_catalog_title_hint();
CREATE FUNCTION refresh_wiki_title_hint() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP<>'INSERT' THEN
        PERFORM refresh_catalog_title_hint(b.card_id) FROM catalog_search_cache b
        WHERE b.game_code=OLD.game_code AND b.title_wiki_key=OLD.lookup_key ORDER BY b.card_id;
    END IF;
    IF TG_OP='INSERT' OR (TG_OP='UPDATE' AND (NEW.game_code,NEW.lookup_key) IS DISTINCT FROM (OLD.game_code,OLD.lookup_key)) THEN
        PERFORM refresh_catalog_title_hint(b.card_id) FROM catalog_search_cache b
        WHERE b.game_code=NEW.game_code AND b.title_wiki_key=NEW.lookup_key ORDER BY b.card_id;
    END IF;
    RETURN NULL;
END $$;
CREATE TRIGGER catalog_title_wiki AFTER INSERT OR UPDATE OF game_code,lookup_key,names,printing_number,passcode OR DELETE ON wiki_card_document
FOR EACH ROW EXECUTE FUNCTION refresh_wiki_title_hint();
ANALYZE catalog_search_cache;

-- Match announcements through their indexed code or title. A nullable OR across
-- both keys previously compared unrelated pack/announcement pairs on every page.
CREATE INDEX onepiece_label_by_name ON onepiece_pack_label(lower(name),pack_id);
CREATE VIEW catalog_release_candidate AS
WITH automatic AS NOT MATERIALIZED (
    SELECT id,game_code,catalog_code,catalog_name,product_key FROM product_release
    WHERE NOT manual AND selected_pack_id IS NULL
), keys AS (
    SELECT e.id AS release_id,p.id AS pack_id FROM automatic e JOIN visible_catalog_pack p
      ON p.game_code=e.game_code AND upper(p.code)=upper(e.catalog_code)
    WHERE e.catalog_name IS NULL OR lower(p.name)=lower(e.catalog_name)
       OR (p.game_code='ONEPIECE' AND EXISTS(SELECT FROM onepiece_pack_label l WHERE l.pack_id=p.id AND lower(l.name)=lower(e.catalog_name)))
    UNION
    SELECT e.id,p.id FROM automatic e JOIN visible_catalog_pack p
      ON p.game_code=e.game_code AND lower(p.name)=lower(e.catalog_name) WHERE e.catalog_code IS NULL
    UNION
    SELECT e.id,p.id FROM automatic e JOIN onepiece_pack_label l ON lower(l.name)=lower(e.catalog_name)
      JOIN visible_catalog_pack p ON p.id=l.pack_id AND p.game_code=e.game_code
      WHERE e.game_code='ONEPIECE' AND e.catalog_code IS NULL
)
SELECT k.release_id,k.pack_id FROM keys k JOIN automatic e ON e.id=k.release_id JOIN pack p ON p.id=k.pack_id
WHERE CASE WHEN e.game_code='YUGIOH' AND starts_with(e.product_key,'na-premiere:')
           THEN p.metadata @> '{"wp":true,"sec":true}' ELSE starts_with(p.legacy_key,'catalog:') END;

CREATE OR REPLACE VIEW catalog_pack_date AS
WITH unique_match AS (
    SELECT release_id,min(pack_id) AS pack_id FROM catalog_release_candidate GROUP BY release_id HAVING count(*)=1
), matches AS (
    SELECT coalesce(s.superseded_by,s.id) AS pack_id,e.release_date FROM product_release e JOIN pack s ON s.id=e.selected_pack_id
    UNION ALL
    SELECT m.pack_id,e.release_date FROM unique_match m JOIN product_release e ON e.id=m.release_id
), announced AS (SELECT pack_id,min(release_date) AS release_date FROM matches GROUP BY pack_id)
SELECT p.id AS pack_id,p.game_code,coalesce(p.release_date,a.release_date) AS release_date
FROM visible_catalog_pack p LEFT JOIN announced a ON a.pack_id=p.id
WHERE coalesce(p.release_date,a.release_date) IS NOT NULL;
