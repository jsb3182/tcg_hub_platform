"""Publish local catalog changes in the transaction that finishes a YGOPRODeck scan."""
import json
from urllib.parse import quote

from psycopg.types.json import Jsonb

DATABASE_URL = "https://ygoprodeck.com/card-database/"


def notice_text(card_count, pack_count, cards, packs):
    card_unit = "entry" if card_count == 1 else "entries"
    pack_unit = "set" if pack_count == 1 else "sets"
    titles = {
        "ko": "유희왕 도감 신규 등록 내역",
        "en": "New entries in the Yu-Gi-Oh! catalog",
        "ja": "遊戯王カード図鑑の新規登録情報",
    }
    summaries = {
        "ko": f"YGOPRODeck 기준 카드 항목 {card_count}건과 팩 {pack_count}개를 도감에 추가했습니다.",
        "en": f"YGOPRODeck catalog additions include {card_count} card {card_unit} and {pack_count} {pack_unit}.",
        "ja": f"YGOPRODeckの情報に基づき、カード{card_count}件とパック{pack_count}件を図鑑に追加しました。",
    }
    card_labels = {"ko": "카드", "en": "Cards", "ja": "カード"}
    pack_labels = {"ko": "팩", "en": "Sets", "ja": "パック"}
    for lang in titles:
        examples = dict.fromkeys((names or {}).get(lang) or name for name, names in cards)
        if examples:
            summaries[lang] += " " + card_labels[lang] + " · " + ", ".join(examples)
        if packs:
            summaries[lang] += " " + pack_labels[lang] + " · " + ", ".join(packs)
    return {lang: (title, summaries[lang]) for lang, title in titles.items()}


def collect_pack_dates(releases, batch):
    for card in batch:
        if card.get("pack_tcg_date"):
            name = card["pack_name"]
            releases.setdefault(name, {"name": name, "released": card["pack_tcg_date"],
                                       "card_key": "catalog:YUGIOH:" + card["external_id"]})


def publish_notice(db, source_id, key, url, text):
    title, summary = text["ko"]
    payload = {"kind": "NEWS", "title": title, "summary": summary}
    item = db.execute("""
        INSERT INTO feed_item(source_id,external_id,source_url,payload,status,source_published_at)
        SELECT id,%s,%s,%s,CASE WHEN auto_publish THEN 'PUBLISHED' ELSE 'PENDING' END,now()
          FROM feed_source WHERE id=%s ON CONFLICT(source_id,external_id) DO NOTHING RETURNING id
    """, (key, url, Jsonb(payload), source_id)).fetchone()
    if item:
        db.execute("UPDATE feed_item SET original_language='ko',translation_due_at=NULL WHERE id=%s", (item[0],))
        with db.cursor() as cur:
            cur.executemany("INSERT INTO feed_item_translation(item_id,lang,title,summary) VALUES (%s,%s,%s,%s)",
                            [(item[0], lang, *text[lang]) for lang in ("en", "ja")])


def publish_recent_set(db, source_id, releases):
    # Use an explicit TCG set date from this complete API scan, never a card's first OCG/TCG date.
    recent = db.execute("""
        SELECT r.name,r.released FROM jsonb_to_recordset(%s) AS r(name text,released date,card_key text)
          JOIN card observed ON observed.legacy_key=r.card_key AND observed.source_id=%s
         WHERE r.released BETWEEN (now() AT TIME ZONE 'Asia/Seoul')::date-30 AND (now() AT TIME ZONE 'Asia/Seoul')::date
           AND EXISTS (SELECT 1 FROM card c WHERE c.source_id=observed.source_id
                        AND c.pack_id=observed.pack_id AND c.status='PUBLISHED')
         ORDER BY r.released DESC,r.name COLLATE "C" LIMIT 1
    """, (Jsonb(list(releases.values())), source_id)).fetchone()
    if recent:
        name, released = recent
        day = released.isoformat()
        text = {
            "ko": (f"유희왕 TCG 최근 발매 팩 · {name}", f"YGOPRODeck에 기록된 {name}의 TCG 발매일은 {day}입니다."),
            "en": (f"Recent Yu-Gi-Oh! TCG set · {name}", f"YGOPRODeck lists {day} as the TCG release date for {name}."),
            "ja": (f"遊戯王TCGの最近の発売パック · {name}", f"YGOPRODeckによると、{name}のTCG発売日は{day}です。"),
        }
        publish_notice(db, source_id, "catalog-recent-set:v1", f"https://ygoprodeck.com/pack/{quote(name.lower(), safe='')}/", text)


def finish_yugioh_scan(db, source_id, releases):
    # Batch upserts can survive an interrupted import. Advance both watermarks only on full success.
    stored = db.execute("SELECT cursor_value FROM feed_source WHERE id=%s FOR UPDATE", (source_id,)).fetchone()[0]
    previous = json.loads(stored or "{}").get("news")
    if previous is None:
        if releases:
            publish_recent_set(db, source_id, releases)
        card_id, pack_id = db.execute("""
            SELECT coalesce(max(id),0),coalesce(max(pack_id),0) FROM card
             WHERE source_id=%s AND status='PUBLISHED'
        """, (source_id,)).fetchone()
        return {"card": card_id, "pack": pack_id}

    cards = db.execute("""
        SELECT name,specs->'names',count(*) OVER(),max(id) OVER() FROM card
         WHERE source_id=%s AND status='PUBLISHED' AND id>%s ORDER BY id LIMIT 3
    """, (source_id, previous["card"])).fetchall()
    packs = db.execute("""
        SELECT p.name,count(*) OVER(),max(p.id) OVER() FROM pack p
         WHERE p.game_code='YUGIOH' AND p.id>%s AND p.name<>'수록 팩 미확인'
           AND EXISTS (SELECT 1 FROM card c WHERE c.pack_id=p.id AND c.source_id=%s AND c.status='PUBLISHED')
         ORDER BY p.id LIMIT 3
    """, (previous["pack"], source_id)).fetchall()
    if not cards and not packs:
        return previous

    high = {"card": cards[0][3] if cards else previous["card"], "pack": packs[0][2] if packs else previous["pack"]}
    text = notice_text(cards[0][2] if cards else 0, packs[0][1] if packs else 0,
                       [(row[0], row[1]) for row in cards], [row[0] for row in packs])
    publish_notice(db, source_id, f"catalog-news:{high['card']}:{high['pack']}", DATABASE_URL, text)
    return high
