"""Rate-limited, resumable secondary catalog imports. No user request calls these services."""
import json
import math
import os
import re
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode,quote
from urllib.error import HTTPError
from bs4 import BeautifulSoup
from psycopg.types.json import Jsonb
from .catalog_sources.transport import CatalogHTTP

KEYS={"APITCG":"APITCG_API_KEY","TCGSTUDIO":"TRADINGCARDSTUDIO_API_KEY","RIOT":"RIOT_API_KEY",
      "POKEWALLET":"POKEWALLET_API_KEY","RIFTCODEX":None,"TCGDEX":None,"YUGIOHKR":None,"WIKI_INDEX":None}
GAMES={"YUGIOH":"yugioh","POKEMON":"pokemon","ONEPIECE":"one-piece-card-game",
       "WEISS":"weiss-schwarz","NIVEL":"nivel-arena","RIFTBOUND":"riftbound"}


def configure(db):
    for provider,key in KEYS.items():
        ready=not key or bool(os.environ.get(key,"").strip())
        db.execute("""insert into provider_configuration values(%s,%s,%s) on conflict(provider)
            do update set requires_key=excluded.requires_key,configured=excluded.configured""",(provider,bool(key),ready))
        if key:
            note=key+" 미설정"
            if ready:
                db.execute("update feed_source set policy_note=null,enabled=true where provider=%s and policy_note=%s",
                           (provider,note))
            else:
                db.execute("update feed_source set enabled=false,policy_note=%s where provider=%s and enabled and policy_note is null",
                           (note,provider))


def clean(text):
    if not isinstance(text,str):return None
    return BeautifulSoup(text,"html.parser").get_text(" ",strip=True)[:8000] if "<" in text else text.strip()[:8000]


def korean_yugioh(db, after, http=None):
    """The reference endpoint identifies cards by name. Require an official CID and both combat stats."""
    http=http or CatalogHTTP()
    targets=db.execute("""select c.id,c.number,p.code,c.specs->'names'->>'ko',c.specs->>'konami_id',
                c.specs->>'atk',c.specs->>'def' from card c join pack p on p.id=c.pack_id
            join feed_source f on f.id=c.source_id and f.provider='CATALOG' and f.source_key='YUGIOH'
            where c.game_code='YUGIOH' and c.status='PUBLISHED' and c.id>%s and p.code is not null
                and c.specs->>'konami_id' ~ '^[1-9][0-9]{0,9}$' and c.specs->>'atk' ~ '^[0-9]+$' and c.specs->>'def' ~ '^[0-9]+$'
                and c.specs->'names'->>'ko' ~ '[가-힣]' and nullif(c.specs->'texts'->>'ko','') is null
            order by c.id limit 4""",(int(after or 0),)).fetchall()
    rows=[]
    for cid,number,code,name,konami,atk,defense in targets:
        url="https://api.yugiohcard.kr/card/"+quote(name,safe="")
        try:
            data=json.loads(http.get(url,ttl=604800,size=65536,delay=2).read_bytes())
        except HTTPError as error:
            if error.code!=404:raise
            error.close()
            continue
        if (data.get("cardName")!=name or not re.fullmatch(r"공격력\s*"+atk,str(data.get("cardAtk","")))
                or not re.fullmatch(r"수비력\s*"+defense,str(data.get("cardDef","")))):continue
        effect=clean(data.get("cardText"))
        if not effect or not re.search("[가-힣]",effect):continue
        rows.append(dict(id=str(cid),number=number,packCode=code,name=name,lang="ko",effect=effect,
                         sourceUrl=url,facts={"konamiId":konami,"atk":atk,"def":defense}))
    return rows,str(targets[-1][0]) if len(targets)==4 else None


def fetch(provider,game,cursor,http=None):
    http=http or CatalogHTTP()
    delay=max(1,min(300,float(os.environ.get("TCG_PROVIDER_INTERVAL_SECONDS","2"))))
    def read(url,headers=None,ttl=86400):
        return json.loads(http.get(url,headers=headers,ttl=ttl,size=12_000_000,delay=delay).read_bytes())
    if provider in ("RIOT","RIFTCODEX"):
        from .catalog_sources.rift_supplement import fetch_page
        return fetch_page(provider,cursor)
    if provider=="TCGDEX":
        # Each language uses its own printing identity and source. Equal set codes do not prove equal artwork.
        languages=("ko","en","ja")
        lang,offset=(cursor or "ko:0").split(":")
        if lang not in languages: raise ValueError("Invalid TCGdex language checkpoint")
        base="https://api.tcgdex.net/v2/"+lang+"/cards"
        cards=read(base)
        start=int(offset)
        chunk=cards[start:start+8]
        rows=[]
        for card in chunk:
            ident=card["id"]
            url=base+"/"+quote(ident,safe="")
            item=read(url,ttl=7*86400)
            if item.get("id")!=ident or not item.get("localId"):continue
            text=[a.get("effect") for k in ("abilities","attacks") for a in item.get(k,[]) if a.get("effect")]
            facts={k:item[k] for k in ("hp","types","stage","regulationMark","category") if item.get(k) is not None}
            rows.append(dict(id=lang+":"+ident,number=item["localId"],packCode=item["set"]["id"],packName=item["set"].get("name"),
                             name=item["name"],lang=lang,
                             sourceUrl=url,effect="\n".join(text) or item.get("effect"),facts=facts))
            art=item.get("image")
            if isinstance(art,str) and art.startswith("https://assets.tcgdex.net/"+lang+"/"):
                from .local_art import provider as accepted_image
                full=art.rstrip("/")+"/high.webp"
                if accepted_image(full):
                    rows[-1]["image"]=full
        if start+len(chunk)<len(cards): return rows,lang+":"+str(start+len(chunk))
        index=languages.index(lang)+1
        return rows,languages[index]+":0" if index<len(languages) else None
    headers={"X-API-Key":os.environ[KEYS[provider]]}
    if provider=="POKEWALLET":
        base="https://api.pokewallet.io"
        sets=sorted((s for s in read(base+"/sets",headers)["data"] if s.get("language")=="eng" and s.get("set_id")),
                    key=lambda s:str(s["set_id"]))
        if not sets: return [],None
        position,page=(cursor or [None,1])
        group=next((s for s in sets if position is None or str(s["set_id"])>=position),None)
        if group is None: return [],None
        gid=str(group["set_id"])
        if position!=gid: page=1
        url=base+"/sets/"+quote(gid,safe="")
        body=read(url+"?"+urlencode({"page":page,"limit":50}),headers)
        if str(body["set"]["set_id"])!=gid: raise ValueError("Mismatched Pokémon set")
        rows=[]
        for row in body["cards"]:
            card=row["card_info"]
            if card.get("product_type")!="card" or not card.get("card_number"):continue
            prices=[{"market":"TCGplayer "+p["sub_type_name"],"amount":p["market_price"],"currency":"USD","time":p["updated_at"]}
                    for p in (row.get("tcgplayer") or {}).get("prices") or []
                    if p.get("sub_type_name") and p.get("updated_at") and p.get("market_price") is not None]
            rows.append(dict(id=str(row["id"]),number=card["card_number"],name=card["name"],packCode=group.get("set_code"),
                packName=group["name"],lang="en",effect=clean(card.get("card_text")),
                facts={k:card[k] for k in ("stage","hp","rarity","variants") if card.get(k) is not None},
                sourceUrl=base+"/cards/"+quote(str(row["id"]),safe=""),prices=prices))
        if page*50<body["set"]["total_cards"]: return rows,[gid,page+1]
        following=next((str(s["set_id"]) for s in sets if str(s["set_id"])>gid),None)
        return rows,[following,1] if following else None
    if provider=="TCGSTUDIO":
        offset=int(cursor or 0)
        base="https://api.tradingcardstudio.com/v1/cards"
        body=read(base+"?"+urlencode({"game":GAMES[game],"limit":8,"offset":offset}),headers)
        rows=[]
        for row in body["data"]:
            if row.get("game_slug")!=GAMES[game] or not row.get("card_number"):continue
            url=base+"/"+quote(str(row["id"]),safe="")
            detail=read(url,headers)["data"]
            if detail.get("id")!=row["id"]:raise ValueError("Mismatched provider printing")
            attrs=detail.get("attributes") or {}
            prices=[{"currency":p["currency_code"],"amount":p["price_amount"],"time":p.get("captured_at"),
                     "market":p.get("market","")} for p in detail.get("latest_prices") or []
                    if p.get("price_type")=="market" and p.get("mapping_scope")=="exact_print" and p.get("price_amount") is not None]
            rows.append(dict(id=str(row["id"]),number=row["card_number"],packCode=row.get("set_code"),name=row["name"],
                     lang=row.get("language_code","und"),sourceUrl=url,facts=attrs,effect=clean(attrs.get("effect")),prices=prices))
        return rows,str(offset+len(body["data"])) if len(body["data"])==8 and offset+8<body["pagination"]["total"] else None
    if provider!="APITCG":raise ValueError("Unsupported supplemental source")
    page=int(cursor or 1)
    body=read("https://api.apitcg.com/api/products?"+urlencode({"tcg":"one-piece","type":"card","page":page,"limit":50}),headers)
    rows=[]
    for row in body["data"]:
        attrs=row.get("attributes") or {}
        if row.get("type")!="card" or (row.get("tcg") or {}).get("_id")!="one-piece" or not attrs.get("Number"):continue
        price=(row.get("markets") or {}).get("tcgplayer") or {}
        amount=(price.get("prices") or {}).get("market")
        facts={k:clean(v) for k,v in attrs.items() if k!="Description"}
        for key,out in {"CardType":"type","Cost":"cost","Color":"color","Power":"power","Rarity":"rarity"}.items():
            if facts.get(key): facts[out]=facts[key]
        rows.append(dict(id=str(row["_id"]),number=attrs["Number"],packCode=(row.get("set") or {}).get("code"),
            packName=(row.get("set") or {}).get("name"),name=row["name"],lang="en",facts=facts,effect=clean(attrs.get("Description")),
            sourceUrl="https://api.apitcg.com/api/products/"+str(row["_id"]),
            prices=[] if amount is None else [{"currency":"USD","amount":amount,"market":"TCGplayer "+str(price.get("printing") or ""),"time":row.get("updatedAt")}]))
    return rows,str(page+1) if len(body["data"])==50 and page*50<(body.get("total") or math.inf) else None


def save(db,source,rows):
    from .sync import save_cards
    game,provider=source["game_code"],source["provider"]
    changed=0
    for row in rows:
        number=str(row.get("number") or "").strip()
        if not number or len(number)>128 or not row.get("name") or not row.get("id"):continue
        code=str(row.get("packCode") or "").strip()
        if game=="RIFTBOUND" and number.count("-")==2:
            first,denominator=number.rsplit("-",1)
            if denominator.isdigit(): number=first.upper()+"/"+denominator
        identity=f"{provider}:{row['id']}"
        own_key=f"catalog:{game}:{identity}"
        lang=row.get("lang","und")
        if lang not in ("ko","en","ja"):lang="und"
        candidates=db.execute("""select c.id,c.legacy_key,p.code,c.name,c.original_name,c.specs->'names'
            from card c left join pack p on p.id=c.pack_id where c.game_code=%s and lower(c.number)=lower(%s)
            and c.status='PUBLISHED'""",(game,number)).fetchall()
        exact=[r[0] for r in candidates if r[1]==own_key]
        if not exact and code:
            exact=[r[0] for r in candidates if (r[2] or "").lower()==code.lower() and row["name"].casefold() in
                   {str(n).casefold() for n in (r[3],r[4],*(r[5] or {}).values()) if n}]
        cid=exact[0] if len(exact)==1 else None
        if provider=="YUGIOHKR":
            target=db.execute("""select id from card where id=%s and game_code='YUGIOH' and number=%s and status='PUBLISHED'
                and specs->'names'->>'ko'=%s and specs->>'konami_id'=%s and specs->>'atk'=%s and specs->>'def'=%s""",
                (int(row["id"]),number,row["name"],row["facts"]["konamiId"],row["facts"]["atk"],row["facts"]["def"])).fetchone()
            if not target:continue
            cid=target[0]
        # A secondary source can add a verified missing printing. An ambiguous match stays in observations for review.
        if (not candidates or own_key in {r[1] for r in candidates}) and code and provider not in ("RIFTCODEX","YUGIOHKR"):
            facts=row.get("facts") or {}
            fields=("hp","types","category","type","power","cost","color","life","level","stage","soul","energy","might","regulationMark")
            specs={k:facts[k] for k in fields if facts.get(k) is not None}
            specs.update(language=lang,names={lang:row["name"]},sources={lang:row["sourceUrl"]})
            if provider=="TCGDEX" and row.get("image"):
                specs.update(images={lang:row["image"]},imageSources={lang:row["sourceUrl"]},imageProducts={lang:code})
            if row.get("effect"):
                specs["texts"]={lang:row["effect"]}
            card=dict(external_id=identity,pack_code=code,pack_name=row.get("packName") or code,number=number,name=row["name"],
                      original_name=row["name"],rarity=clean(facts.get("rarity") or facts.get("Rarity")),effect=row.get("effect"),specs=specs,source_url=row["sourceUrl"])
            changed+=save_cards(db,source,[card])
            cid=db.execute("select id from card where legacy_key=%s",(own_key,)).fetchone()[0]
        db.execute("""insert into supplemental_printing as s(provider,game_code,external_id,card_id,pack_code,number,name,lang,effect,facts,source_url)
            values(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) on conflict(provider,game_code,external_id) do update set
            (card_id,pack_code,number,name,lang,effect,facts,source_url,updated_at)=(excluded.card_id,excluded.pack_code,excluded.number,
            excluded.name,excluded.lang,excluded.effect,excluded.facts,excluded.source_url,now())
            where (s.card_id,s.pack_code,s.number,s.name,s.lang,s.effect,s.facts,s.source_url) is distinct from
            (excluded.card_id,excluded.pack_code,excluded.number,excluded.name,excluded.lang,excluded.effect,excluded.facts,excluded.source_url)""",
            (provider,game,str(row["id"]),cid,code,number,row["name"],lang,row.get("effect"),Jsonb(row.get("facts") or {}),row["sourceUrl"]))
        if cid and row.get("prices"):
            variants=db.execute("select id from card_variant where card_id=%s order by position limit 2",(cid,)).fetchall()
            if len(variants)==1:
                for p in row["prices"]:
                    if p.get("currency") not in ("USD","EUR","KRW","JPY") or not p.get("time"):continue
                    try: amount=Decimal(str(p["amount"]))
                    except (InvalidOperation,KeyError):continue
                    if not amount.is_finite() or not 0<=amount<10**14:continue
                    market=str(p.get("market") or "").strip()[:160]
                    listing=db.execute("""insert into price_listing as p(variant_id,provider,external_key,source_url,market) values (%s,%s,%s,%s,%s)
                        on conflict(provider,external_key) do update set source_url=excluded.source_url,market=excluded.market
                        where p.variant_id=excluded.variant_id returning id""",
                        (variants[0][0],provider,identity+":"+market+":"+p["currency"],row["sourceUrl"],market or None)).fetchone()
                    if listing:
                        db.execute("""insert into price_snapshot(listing_id,observed_at,currency,amount) values(%s,%s,%s,%s)
                            on conflict(listing_id,observed_at) do nothing""",(listing[0],p["time"],p["currency"],amount))
    return changed
