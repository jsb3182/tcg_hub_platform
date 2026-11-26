"""Optional Pokémon TCG API v2 English printings, with its maintainer's snapshot for outages."""
import json
import logging
import os
import re
import tarfile
import tempfile
import time
from pathlib import Path, PurePosixPath
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit

from ..feeds import backoff

LOG = logging.getLogger(__name__)
REPO = "PokemonTCG/pokemon-tcg-data"
API = "https://api.pokemontcg.io/v2"
WEEK = 7 * 86400
IDENT = re.compile(r"[A-Za-z0-9._-]{1,100}")


def cache_json(path, data):
    fd, name = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf8") as out:
            json.dump(data, out, separators=(",", ":"), ensure_ascii=False)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def printing(row, group):
    ident, number, name = row.get("id"), row.get("number"), row.get("name")
    if not all(isinstance(v,str) and v for v in (ident,group,number,name)) or not IDENT.fullmatch(ident) or not IDENT.fullmatch(group):
        return None
    if not ident.startswith(group + "-"):
        return None
    images = row.get("images") or {}
    image = images.get("large") or images.get("small") or ""
    url = urlsplit(image)
    if url.scheme!="https" or url.netloc!="images.pokemontcg.io" or not re.fullmatch(
            "/"+re.escape(group)+r"/[A-Za-z0-9_.-]+\.png",url.path) or url.query or url.fragment:
        return None
    return [ident, group, number.lstrip("0") or "0", name, image]


def backup(http, revision):
    cache = http.root / ".pokemontcg-backup-v1.json"
    previous = json.loads(cache.read_text("utf8")) if cache.is_file() else {}
    try:
        sha = revision(http, REPO, None)
        if previous.get("revision")==sha:
            return previous
        archive=http.get(f"https://codeload.github.com/{REPO}/tar.gz/{sha}", ttl=365*86400,
                         size=48_000_000, family="pokemontcg-provider-archive")
        rows, sets = [], []
        with tarfile.open(archive,"r|gz") as files:
            for entry in files:
                files.members.clear()
                parts=PurePosixPath(entry.name).parts[1:]
                if not entry.isfile() or not (parts==("sets","en.json") or len(parts)==3 and parts[:2]==("cards","en") and parts[2].endswith(".json")):
                    continue
                if not 0<entry.size<=3_000_000: raise ValueError("Oversized Pokémon provider file")
                with files.extractfile(entry) as reader:
                    values=json.load(reader)
                if parts==("sets","en.json"):
                    sets=[[v["id"],v.get("ptcgoCode")] for v in values]
                else:
                    group=parts[2][:-5]
                    rows.extend(p for row in values if (p:=printing(row,group)))
        if not sets or not rows: raise ValueError("Empty Pokémon provider archive")
        result={"revision":sha,"sets":sets,"rows":rows}
        cache_json(cache,result)
        return result
    except (OSError,ValueError,KeyError,tarfile.TarError) as exc:
        if isinstance(exc, HTTPError): exc.close()
        LOG.warning("Pokémon English backup deferred (%s)",type(exc).__name__)
        return previous


def live(http, candidates, *, now=None):
    """Refresh the complete set directory and at most four exact printing IDs per week."""
    now=time.time() if now is None else now
    cache=http.root / ".pokemontcg-rest-v1.json"
    state=json.loads(cache.read_text("utf8")) if cache.is_file() else {}
    if state.get("next",0)>now: return state
    wait=WEEK
    try:
        page, expected, sets = 1, None, []
        while expected is None or len(sets)<expected:
            query={"select":"id,ptcgoCode","pageSize":250}
            if page>1: query["page"]=page
            file=http.get(API+"/sets?"+urlencode(query),ttl=WEEK,size=2_000_000,delay=2.1)
            body=json.loads(file.read_text("utf8"))
            items=body["data"]
            if expected is None: expected=body["totalCount"]
            if not 0<expected<=10000 or expected!=body["totalCount"] or body.get("page")!=page or not items or len(items)!=body["count"]:
                raise ValueError("Incomplete Pokémon sets response")
            sets.extend([r["id"],r.get("ptcgoCode")] for r in items)
            page+=1
        if len(sets)!=expected or len({r[0] for r in sets})!=expected: raise ValueError("Duplicate Pokémon sets")
        state["sets"]=sets
        rows=state.setdefault("cards",{})
        # Rotate through known real API IDs. A provider error keeps all earlier verified
        # observations; a removed ID is retried only on a later pass.
        ids=sorted(candidates)
        cursor=state.get("after","")
        batch=([i for i in ids if i>cursor]+[i for i in ids if i<=cursor])[:4]
        for ident in batch:
            state["after"]=ident
            try:
                file=http.get(API+"/cards/"+ident,ttl=WEEK,size=160_000,delay=2.1)
            except HTTPError as exc:
                if exc.code!=404: raise
                exc.close()
                rows.pop(ident,None)
                continue
            card=json.loads(file.read_text("utf8"))["data"]
            group=card["set"]["id"]
            record=printing(card,group)
            if not record or record[0]!=ident or record[1:4]!=candidates[ident][1:4]:
                raise ValueError("Pokémon API printing did not match the expected set, number and name")
            rows[ident]=record
    except (OSError,ValueError,KeyError,TypeError) as exc:
        if isinstance(exc,HTTPError):
            wait=max(wait,backoff(exc.headers or {}))
            exc.close()
        LOG.warning("Pokémon TCG REST supplement deferred (%s)",type(exc).__name__)
    state["next"]=now+wait
    cache_json(cache,state)
    return state


def english_art(http, revision, tcgdex):
    stored=backup(http,revision)
    candidates={row[0]:row for row in stored.get("rows",[])}
    recent=live(http,candidates)
    aliases=dict(stored.get("sets",[]))
    aliases.update({key:value for key,value in recent.get("sets",[]) if value})
    art={}
    def add(group,number,name,image,source):
        for key in (group,aliases.get(group)):
            if key:
                art[key.lower(),number,name]=(image,source)
    sha=stored.get("revision","")
    for ident,group,number,name,image in candidates.values():
        add(group,number,name,image,f"https://github.com/{REPO}/blob/{sha}/cards/en/{group}.json")
    # Keep TCGdex as the primary source wherever the original integration has evidence.
    for row in tcgdex:
        number=str(row.get("localId") or "")
        ident=row.get("id") or ""
        base=row.get("image") or ""
        url=urlsplit(base)
        if not number or not ident.endswith("-"+number) or url.scheme!="https" or url.netloc!="assets.tcgdex.net" or not url.path.startswith("/en/"):
            continue
        add(ident[:-len(number)-1],number.lstrip("0") or "0",row["name"],base+"/high.webp",
            "https://api.tcgdex.net/v2/en/cards/"+ident)
    # A positively verified live printing may supersede its historical source.
    for ident,group,number,name,image in recent.get("cards",{}).values():
        add(group,number,name,image,API+"/cards/"+ident)
    return art
