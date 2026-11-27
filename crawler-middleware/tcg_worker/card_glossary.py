"""Terms are protected during local inference. Drop a result if even one marker changes."""
import re


TERMS = {
    "YUGIOH": {"special summon":"특수 소환","graveyard":"묘지","gy":"묘지","banish":"제외","extra deck":"엑스트라 덱",
               "negate the effect":"효과를 무효","chain":"체인","tribute":"릴리스","hand":"패","deck":"덱",
               "特殊召喚":"특수 소환","墓地":"묘지","除外":"제외","手札":"패","デッキ":"덱","リリース":"릴리스"},
    "POKEMON": {"discard pile":"트래쉬","knocked out":"기절","bench":"벤치","active spot":"배틀필드","ability":"특성",
                "energy":"에너지","supporter":"서포트","item":"아이템","stadium":"스타디움","トラッシュ":"트래쉬","きぜつ":"기절",
                "ベンチ":"벤치","特性":"특성","エネルギー":"에너지"},
    "ONEPIECE": {"don!!":"돈!!","rested":"레스트","rest":"레스트","active":"액티브","counter":"카운터","trigger":"트리거",
                 "blocker":"블로커","rush":"속공","k.o.":"KO","ドン!!":"돈!!","レスト":"레스트","アクティブ":"액티브",
                 "カウンター":"카운터","トリガー":"트리거","ブロッカー":"블로커","速攻":"속공"},
    "WEISS": {"waiting room":"대기실","climax":"클라이맥스","stock":"스톡","clock":"클락","memory":"추억","reverse":"리버스",
              "rest":"레스트","soul":"소울","encore":"앙코르","控え室":"대기실","クライマックス":"클라이맥스",
              "ストック":"스톡","クロック":"클락","思い出":"추억","ソウル":"소울","アンコール":"앙코르"},
    "NIVEL": {"leader":"리더","unit":"유닛","skill":"스킬","item":"아이템","cost":"코스트","power":"파워","hit":"히트",
              "trigger":"트리거","リーダー":"리더","ユニット":"유닛","スキル":"스킬","アイテム":"아이템"},
    "RIFTBOUND": {"battlefield":"전장","rune":"룬","champion":"챔피언","unit":"유닛","gear":"장비","energy":"에너지",
                  "might":"위력","spell":"주문","ルーン":"룬","チャンピオン":"챔피언","ユニット":"유닛"},
}


def translate_line(model, game, line, lang):
    terms = TERMS[game]
    markers = {}
    def mark(match):
        token=str(87316000+len(markers))
        if token in line:
            raise ValueError("Glossary marker collides with card text")
        markers[token] = terms[match.group().lower()]
        return " " + token + " "
    patterns = [r"(?<![a-zA-Z])"+re.escape(k)+r"(?![a-zA-Z])" if k.isascii() else re.escape(k)
                for k in sorted(terms,key=len,reverse=True)]
    protected = re.sub("|".join(patterns),mark,line,flags=re.I)
    value = model.translate(protected.strip(),lang,"ko")
    if not value or any(value.count(k)!=1 for k in markers):
        return None
    for k, term in markers.items():
        value = value.replace(k,term)
    return value
