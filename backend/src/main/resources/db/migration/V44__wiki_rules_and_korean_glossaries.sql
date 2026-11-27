ALTER TABLE wiki_card_document ADD COLUMN korean_text text CHECK (length(korean_text) BETWEEN 1 AND 8000),
    ADD COLUMN article_details jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(article_details)='object');
ALTER TABLE card_korean_reading DROP CONSTRAINT card_korean_reading_basis_check;
ALTER TABLE card_korean_reading ADD CHECK (basis IN ('MACHINE_TRANSLATION','CURATED_TRANSLATION','GLOSSARY_TRANSLATED'));
UPDATE card_korean_reading SET name=NULL,effect=NULL,due_at=now() WHERE basis='MACHINE_TRANSLATION' AND (name IS NOT NULL OR effect IS NOT NULL);

-- Only a documented advance printing may enter automatic card translation.
CREATE FUNCTION advance_printing(c card) RETURNS boolean LANGUAGE sql STABLE AS $$
    SELECT c.release_date>CURRENT_DATE OR lower(coalesce(c.specs->>'releasePhase','')) IN ('preview','prerelease')
$$;
CREATE VIEW pending_korean_card_reading AS
    SELECT r.card_id,r.due_at FROM card_korean_reading r JOIN card c ON c.id=r.card_id
    WHERE r.due_at IS NOT NULL AND advance_printing(c);
