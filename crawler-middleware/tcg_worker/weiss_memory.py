"""Prepare optional portable M2M100 translation memory on a PC from the public English catalog ZIP."""
import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3
import zipfile
import re

from .catalog_sources.weiss_art import sets
from .catalog_sources.weiss_korean import draft_line, source_effect, showcase, literal_title, rule_line, title_with_people
from .weiss_readings import VERSION, memory_key, memory_revision, translated_fields


class BatchUnit:
    """Collect all model-bound clauses, including later clauses when one has no translation."""
    def __init__(self, values):
        self.values = values
        self.requested = {}

    def translate(self, text, source, target):
        self.requested[text] = None
        return self.values.get(text)


def prepare_gpu(cache, archive, get_model, limit):
    seen = set()
    pending = []
    processed = 0
    values = {}

    def flush():
        if not pending:
            return
        uncached = dict.fromkeys(text for _, unit, _ in pending for text in unit.requested if text not in values)
        if uncached:
            model = get_model()
            inputs, owners = [], []
            for text in uncached:
                pieces = []
                for sentence in re.split(r"(?<=[.!?。！？])\s+|\n+", text):
                    tokens = model.tokenizer.encode(sentence, out_type=str)
                    for offset in range(0, len(tokens), 160):
                        pieces.append(len(inputs))
                        inputs.append(["__en__", *tokens[offset:offset + 160], "</s>"])
                owners.append(pieces)
            results = model.model.translate_batch(inputs, target_prefix=[["__ko__"] for _ in inputs],
                         beam_size=3, max_batch_size=32, max_decoding_length=300, no_repeat_ngram_size=4)
            for text, parts in zip(uncached, owners):
                sentences = []
                for i in parts:
                    tokens = results[i].hypotheses[0]
                    if tokens and tokens[0] == "__ko__":
                        tokens = tokens[1:]
                    sentences.append(model.tokenizer.decode(tokens).strip())
                values[text] = " ".join(sentences) if sentences and all(sentences) else None
        for key, unit, immediate in pending:
            if unit.requested:
                _, kind, family, original = key
                immediate = draft_line(lambda: unit, kind, original, family)
            cache.execute("INSERT INTO readings VALUES (?,?,?,?,?)", (*key, immediate))
        cache.commit()
        pending.clear()

    def queue(kind, original, family):
        nonlocal processed
        family=family if kind=="name" else ""
        key=(memory_revision(kind,original,family),kind,family,original)
        if key in seen or (limit is not None and processed>=limit):
            return
        seen.add(key)
        if cache.execute("SELECT 1 FROM readings WHERE revision=? AND kind=? AND family=? AND original=?",key).fetchone():
            return
        unit=BatchUnit(values)
        immediate=draft_line(lambda:unit,kind,original,family)
        pending.append((key,unit,immediate))
        processed+=1
        if len(pending)>=96:
            flush()

    prints=set()
    for _,rows in sets(archive):
        for card in rows:
            code=card["code"].strip()
            if code in prints:
                continue
            prints.add(code)
            family=code.partition("/")[0]
            original=card["name"].strip()
            related=showcase().get(code,{})
            if ((related.get("name"),related.get("product"))!=(card["name"],card["expansion"])
                    and not literal_title(original,family)):
                queue("name",original,family)
                if (parts:=title_with_people(original,family)) and parts[0]:
                    queue("name",parts[0],family)
            effect=source_effect(card["ability"])
            if effect:
                for line in effect.splitlines():
                    if line.strip() and not rule_line(line):
                        queue("rule",line.strip(),"")
    flush()
    return processed


def build(archive, directory, memo, output, limit, threads, device="cpu"):
    from .translation import OfflineTranslator
    model = None
    def get_model():
        nonlocal model
        if model is None:
            model = OfflineTranslator(directory, threads=threads, device=device)
        return model

    stats = Counter()
    with sqlite3.connect(memo) as cache, zipfile.ZipFile(archive) as source:
        cache.execute("CREATE TABLE IF NOT EXISTS readings (revision text,kind text,family text,original text,translated text,"
                      "PRIMARY KEY(revision,kind,family,original))")
        if device=="cuda":
            stats["attempted"]=prepare_gpu(cache,source,get_model,limit)

        def translate(kind, value, group):
            family = group if kind=="name" else ""
            key=(memory_revision(kind,value,family),kind,family,value)
            row=cache.execute("SELECT translated FROM readings WHERE revision=? AND kind=? AND family=? AND original=?",key).fetchone()
            if row is not None:
                return row[0]
            if device=="cuda" or (limit is not None and stats["attempted"]>=limit):
                return None
            translated=draft_line(get_model,kind,value,family)
            cache.execute("INSERT INTO readings VALUES (?,?,?,?,?)",(*key,translated))
            stats["attempted"]+=1
            if stats["attempted"] % 32 == 0:
                cache.commit()
            return translated

        seen=set()
        for _, cards in sets(source):
            for card in cards:
                code=card["code"].strip()
                if code in seen:
                    continue
                seen.add(code)
                official=showcase().get(code,{})
                regional_name=(official.get("name"),official.get("product"))==(card["name"],card["expansion"])
                name,effect,_,_=translated_fields({"number":code,"name":card["name"].strip(),"effect":source_effect(card["ability"]),
                                                    "need_name":not regional_name,"need_effect":True},translate)
                stats["names"]+=bool(name or regional_name)
                stats["effects"]+=bool(effect)
        if not seen:
            raise ValueError("Empty English catalog ZIP")
        cache.commit()
        stats["prints"]=len(seen)
        temp=output.with_name(output.name+".tmp")
        with gzip.open(temp,"wt",encoding="utf8",newline="\n") as out:
            out.write(json.dumps({"version":VERSION})+"\n")
            for revision,kind,family,original,translated in cache.execute(
                    "SELECT revision,kind,family,original,translated FROM readings WHERE revision=? OR revision LIKE ? "
                    "ORDER BY kind,family,original",(VERSION,VERSION+"/%")):
                if revision!=memory_revision(kind,original,family):
                    continue
                key=memory_key(kind,original,family).hex()
                out.write(json.dumps([kind,family,original,translated,key],ensure_ascii=False,separators=(",",":"))+"\n")
                stats["memoEntries"]+=1
        temp.replace(output)
    return dict(stats)


def import_memory(db, path, expected):
    if path.stat().st_size>32*1024*1024 or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
        raise ValueError("Invalid memo file SHA-256 or size")
    added=0
    with gzip.open(path,"rt",encoding="utf8") as stream, db.transaction():
        if json.loads(stream.readline(1024))!={"version":VERSION}:
            raise ValueError("Incompatible translation memory")
        count=0
        while line:=stream.readline(18000):
            count+=1
            if count>120000 or not line.endswith("\n"):
                raise ValueError("Oversize translation memory")
            kind,family,original,translated,signature=json.loads(line)
            if (kind not in ("name","rule") or not isinstance(family,str) or len(family)>32
                    or not isinstance(original,str) or not 1<=len(original)<=1800
                    or (translated is not None and (not isinstance(translated,str) or not 1<=len(translated)<=2200))):
                raise ValueError("Malformed translation unit")
            digest=memory_key(kind,original,family)
            if digest.hex()!=signature:
                continue  # A newer verified spelling changes only translations containing that name.
            added+=db.execute("""
                INSERT INTO weiss_translation_memory(source_hash,original,translated) VALUES(%s,%s,%s)
                ON CONFLICT DO NOTHING
                """,(digest,original,translated)).rowcount
    return added


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ("archive","model","memo","output"):
        parser.add_argument(name,type=Path)
    parser.add_argument("--limit",type=int,help="maximum new inference attempts this run; the next run resumes")
    parser.add_argument("--threads",type=int,default=2,choices=range(1,9))
    parser.add_argument("--device",choices=("cpu","cuda"),default="cpu",help="PC preparation only; phone inference always uses CPU")
    args=parser.parse_args()
    if args.limit is not None and args.limit<0:
        parser.error("Limit must be nonnegative")
    print(json.dumps(build(args.archive,args.model,args.memo,args.output,args.limit,args.threads,args.device)))


if __name__=="__main__":
    main()
