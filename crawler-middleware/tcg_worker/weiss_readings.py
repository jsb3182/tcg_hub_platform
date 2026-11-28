"""Local Korean readings for English Weiss printings. No publisher or inference network requests."""
from collections import Counter
from hashlib import sha256
from urllib.parse import quote

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .catalog_sources.weiss_korean import complete_effect, draft_line, language_metadata, literal_title, rule_line
from .catalog_sources.weiss_korean import PEOPLE, title_with_people
from .catalog_sources.weiss_character_names import character_references

VERSION = "weiss-ko-v2/m2m100-418m-int8"
GLOSSARY = "GLOSSARY_TRANSLATED"
MACHINE = "MACHINE_TRANSLATION"


def eligible(card):
    number = card["number"]
    return bool(number and card["legacy_key"] == "catalog:WEISS:en:"+number
                and card["source_url"] == "https://en.ws-tcg.com/cardlist/cardsearch/exec?cardno="+quote(number,safe=""))


def memory_revision(kind,source,family):
    if kind == "rule":
        return VERSION + "/clause-edition-2"
    if family == "CCS" and "Cardcaptor Sakura" in source:
        return VERSION + "/work-title-1"
    refs = character_references(source, family)
    changed = [(r["english"],r["korean"]) for r in refs if PEOPLE.get(family,{}).get(r["english"])!=r["korean"]]
    if not changed:
        return VERSION
    return VERSION+"/"+sha256(repr(sorted(changed)).encode()).hexdigest()


def memory_key(kind,source,family):
    return sha256("\0".join((memory_revision(kind,source,family),kind,family if kind=="name" else "",source)).encode()).digest()


def lookup(db, get_model, kind, source, family):
    # Rules do not depend on the title franchise. A homonym in a card name may.
    family = family if kind == "name" else ""
    digest = memory_key(kind,source,family)
    row = db.execute("SELECT original,translated FROM weiss_translation_memory WHERE source_hash=%s",(digest,)).fetchone()
    if row is not None:
        if row[0] != source:
            raise ValueError("Translation memory origin mismatch")
        return row[1]
    result = draft_line(get_model,kind,source,family)
    db.execute("""
        INSERT INTO weiss_translation_memory(source_hash,original,translated) VALUES(%s,%s,%s)
        ON CONFLICT DO NOTHING
        """,(digest,source,result))
    return result


def translated_fields(card, translate=None):
    family = card["number"].partition("/")[0]
    name, effect = None, None
    name_basis, effect_basis = None, None
    if card["need_name"]:
        name = literal_title(card["name"], family)
        if name:
            name_basis = GLOSSARY
        elif translate:
            name = translate("name",card["name"],family)
            if not name and (parts:=title_with_people(card["name"],family)):
                phrase, people=parts
                value=translate("name",phrase,family) if phrase else None
                if value and len(value)+len(people)+2<=320:
                    name=value+", "+people
            name_basis = MACHINE if name else None
    original = card["effect"]
    if card["need_effect"] and original and original.strip() not in ("-", "?", "N/A"):
        effect = complete_effect(original)
        if effect:
            effect_basis = GLOSSARY
        elif translate and len(original) <= 8000:
            lines = []
            for line in original.splitlines():
                if line.strip():
                    value = rule_line(line) or translate("rule",line.strip(),family)
                    if not value:
                        break
                    lines.append(value)
            else:
                effect = "\n".join(lines)
                if effect and len(effect) <= 8000:
                    effect_basis = MACHINE
                else:
                    effect = None
    return name,effect,name_basis,effect_basis


def seed_templates(db, keys=None, use_memory=False):
    """Apply deterministic complete fields now, leaving other fields eligible for the model.

    The caller supplies the current import batch. The maintenance CLI pages by card ID.
    """
    if not keys:
        return 0
    with db.cursor(row_factory=dict_row) as cur:
        cards = cur.execute("""
            SELECT c.id,c.number,c.name,c.effect,c.source_url,c.legacy_key,
                   nullif(c.specs->'names'->>'ko','') IS NULL AND r.name IS NULL AS need_name,
                   nullif(c.specs->'texts'->>'ko','') IS NULL AND r.effect IS NULL AS need_effect,
                   nullif(c.specs->'names'->>'ko','') IS NULL AND r.name IS NOT NULL
                       AND coalesce(r.name_basis,r.basis)='MACHINE_TRANSLATION' AS draft_name,
                   nullif(c.specs->'texts'->>'ko','') IS NULL AND r.effect IS NOT NULL
                       AND coalesce(r.effect_basis,r.basis)='MACHINE_TRANSLATION' AS draft_effect,
                   r.due_at
            FROM card c JOIN card_korean_reading r ON c.id=r.card_id
            WHERE c.game_code='WEISS' AND c.status='PUBLISHED' AND c.specs->>'language'='en'
              AND c.legacy_key=ANY(%s) AND (r.due_at IS NOT NULL OR r.basis<>'CURATED_TRANSLATION')
              AND (r.name IS NULL OR r.effect IS NULL OR coalesce(r.name_basis,r.basis)='MACHINE_TRANSLATION'
                       OR coalesce(r.effect_basis,r.basis)='MACHINE_TRANSLATION') FOR UPDATE OF c,r
            """,(list(keys),)).fetchall()
        translate = None
        if use_memory:
            candidates=set()
            for card in cards:
                if eligible(card):
                    if card["need_name"]:
                        family=card["number"].partition("/")[0]
                        candidates.add(memory_key("name",card["name"],family))
                        if (parts:=title_with_people(card["name"],family)) and parts[0]:
                            candidates.add(memory_key("name",parts[0],family))
                    if card["need_effect"] and card["effect"]:
                        candidates.update(memory_key("rule",line.strip(),"") for line in card["effect"].splitlines() if line.strip())
            units={digest:(original,value) for digest,original,value in db.execute("""
                SELECT source_hash,original,translated FROM weiss_translation_memory
                WHERE source_hash=ANY(%s::bytea[]) AND translated IS NOT NULL
                """,(list(candidates),))}

            def translate(kind, original, family):
                entry=units.get(memory_key(kind,original,family))
                return entry[1] if entry and entry[0]==original else None

        count = 0
        for card in cards:
            if not eligible(card):
                continue
            name,effect,nb,eb = translated_fields(card,translate)
            if card["draft_name"] and (verified:=literal_title(card["name"],card["number"].partition("/")[0])):
                name,nb=verified,GLOSSARY
            if card["draft_effect"] and (verified:=complete_effect(card["effect"])):
                effect,eb=verified,GLOSSARY
            if name or effect:
                # A changed source clears both original reading fields and sets due_at.
                # A finished model attempt with no result must not be continuously requeued.
                count += cur.execute("""
                    UPDATE card_korean_reading SET name=coalesce(%s,name),effect=coalesce(%s,effect),
                        name_basis=CASE WHEN %s::text IS NOT NULL THEN %s ELSE name_basis END,
                        effect_basis=CASE WHEN %s::text IS NOT NULL THEN %s ELSE effect_basis END,
                        weiss_draft_due_at=CASE WHEN %s THEN coalesce(due_at,weiss_draft_due_at) END,
                        due_at=NULL,basis=CASE WHEN name IS NULL AND effect IS NULL THEN %s ELSE basis END
                    WHERE card_id=%s
                    """,(name,effect,name,nb,effect,eb,
                         bool((card["need_name"] and not name) or (card["need_effect"] and card["effect"] and not effect)),
                         MACHINE if MACHINE in (nb,eb) else GLOSSARY,card["id"])).rowcount
        return count


def refresh_metadata(db, keys):
    """Build only missing reading metadata from the public card's existing English source fields."""
    changes = []
    with db.cursor(row_factory=dict_row) as cur:
        rows = cur.execute("""
            SELECT c.id,c.number,c.legacy_key,c.name,c.original_name,c.source_url,c.specs,c.effect,p.name AS product
            FROM card c LEFT JOIN pack p ON p.id=c.pack_id
            WHERE c.legacy_key=ANY(%s) AND c.game_code='WEISS' AND c.status='PUBLISHED'
              AND c.specs->>'language'='en' FOR UPDATE OF c
            """,(list(keys),)).fetchall()
        for row in rows:
            if not eligible(row) or row["name"]!=row["original_name"]:
                continue
            specs=row["specs"]
            verified=language_metadata({**specs,"code":row["number"],"name":row["name"],"expansion":row["product"]})
            patch={}
            if "regionalFacts" in verified:
                regional=specs.get("regionalFacts",{})
                if isinstance(regional,dict) and isinstance(regional.get("ko",{}),dict):
                    korean=regional.get("ko",{})
                    combined={**verified["regionalFacts"]["ko"],**korean}
                    if korean!=combined:
                        patch["regionalFacts"]={**regional,"ko":combined}
            if verified.get("characterNameReferences") and "characterNameReferences" not in specs:
                patch["characterNameReferences"]=verified["characterNameReferences"]
            if "names" in verified:
                region_keys=("names","nameBasis","sources","relatedNamePrinting")
                if all(isinstance(specs.get(k,{}),dict) and "ko" not in specs.get(k,{}) for k in region_keys):
                    for key in region_keys:
                        patch[key]={**specs.get(key,{}),"ko":verified[key]["ko"]}
            placeholder=row["effect"] is not None and row["effect"].strip() in ("","-")
            if patch or placeholder:
                changes.append({"id":row["id"],"patch":patch,"placeholder":placeholder})
    if not changes:
        return 0
    return db.execute("""
        UPDATE card c SET specs=c.specs||v.patch,effect=CASE WHEN v.placeholder THEN NULL ELSE c.effect END,
            edit_version=c.edit_version+1 FROM jsonb_to_recordset(%s) AS v(id bigint,patch jsonb,placeholder boolean)
        WHERE c.id=v.id
        """,(Jsonb(changes),)).rowcount


def seed_all(db, stop=None, use_memory=False):
    report = Counter(examined=0,readingsAdded=0,metadataUpdated=0)
    after = 0
    while stop is None or not stop.is_set():
        with db.transaction():
            rows = db.execute("""
                SELECT id,legacy_key FROM card WHERE game_code='WEISS' AND status='PUBLISHED' AND id>%s
                    AND specs->>'language'='en' ORDER BY id LIMIT 160
                """,(after,)).fetchall()
            if not rows:
                break
            keys = [key for _,key in rows]
            report["metadataUpdated"] += refresh_metadata(db,keys)
            report["readingsAdded"] += seed_templates(db,keys,use_memory=use_memory)
            report["examined"] += len(rows)
            after = rows[-1][0]
    return dict(report)
