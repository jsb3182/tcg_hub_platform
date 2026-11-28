"""Korean display aids for verified English Weiss printings. The source edition stays English."""
import re
from collections import Counter
from functools import lru_cache
import json
from pathlib import Path
from .weiss_character_names import character_references, names_for
from .weiss_rule_draft import rule_draft
from .weiss_ability_templates import translate_ability

KOREAN_SHOWCASE = "https://ws-tcg.com/ex/nik_kr/"
ENGLISH_SHOWCASE = "https://en.ws-tcg.com/ex/nik_en/"
_DATA = Path(__file__).with_name("weiss_nikke_korean_names.json")

TRIGGERS = {"SOUL":"소울", "COMEBACK":"컴백", "GATE":"게이트", "TREASURE":"트레저", "CHOICE":"초이스",
            "STANDBY":"스탠바이", "DRAW":"드로", "RETURN":"리턴", "SHOT":"샷", "POOL":"풀"}
TRAITS = {
    "NIKKE":"니케", "Counters":"카운터스", "Heretic":"헬레틱", "Music":"음악", "Weapon":"무기",
    "Magic":"마법", "Avatar":"아바타", "Game":"게임", "Adolescence":"사춘기", "Quintuplets":"다섯 쌍둥이",
    "Adventurer":"모험가", "Fleet Girl":"칸무스", "Master":"마스터", "Servant":"서번트", "Revue":"레뷰",
    "Anniversary":"기념일", "Sports":"스포츠", "Maid":"메이드", "Show Business":"연예계", "Animal":"동물",
    "Death":"죽음", "Cooking":"요리", "Dragon":"드래곤", "Student Council":"학생회", "Demon":"악마",
    "PIXAR":"픽사", "hololive":"홀로라이브", "UMAMUSUME":"우마무스메", "Kivotos":"키보토스",
    "Detective":"탐정", "Police":"경찰", "School":"학교", "Student":"학생", "Teacher":"교사",
    "Pilot":"파일럿", "Love":"사랑", "Ninja":"닌자", "Royalty":"왕족", "Glasses":"안경",
    "Book":"책", "Novel":"소설", "Model":"모델", "Robot":"로봇", "Mecha":"메카", "Twin":"쌍둥이",
    "Twins":"쌍둥이", "Sweets":"과자", "Doll":"인형", "Science":"과학", "Angel":"천사",
    "Sword":"검", "Spirit":"정령", "Family":"가족", "Vampire":"흡혈귀", "Witch":"마녀",
    "Idol":"아이돌", "Human":"인간", "Army":"군대", "Flower":"꽃", "Summer":"여름", "Winter":"겨울",
}


@lru_cache(maxsize=1)
def showcase():
    return {row["code"]: row for row in json.loads(_DATA.read_text("utf8"))}


def known_list(values, terms):
    if not isinstance(values, list):
        return None
    actual = [value for value in values if value not in ("-", "", None)]
    if actual and all(value in terms for value in actual):
        return [terms[value] for value in actual]
    return None


def language_metadata(card):
    facts = {"side": {"W":"바이스","S":"슈발츠"}.get(card.get("side")),
             "triggers": known_list(card.get("trigger"), TRIGGERS),
             "traits": known_list(card.get("attributes"), TRAITS)}
    facts = {key: value for key, value in facts.items() if value}
    metadata = {"regionalFacts":{"ko":facts}} if facts else {}
    references = character_references(card["name"], card["code"].partition("/")[0])
    if references:
        metadata["characterNameReferences"] = references
    printing = showcase().get(card["code"])
    if printing and (card["name"], card.get("expansion")) == (printing["name"], printing["product"]):
        metadata.update(names={"ko":printing["ko"]}, nameBasis={"ko":"RELATED_PRINTING"},
                        sources={"ko":KOREAN_SHOWCASE},
                        relatedNamePrinting={"ko":{"number":printing["relatedNumber"], "englishNumber":printing["publisherEnglishNumber"], "englishSource":ENGLISH_SHOWCASE}})
    return metadata


def source_effect(ability):
    lines = ability or []
    return "\n".join(lines) if any(line.strip() not in ("", "-") for line in lines) else None


# Each mapping covers a whole ability line, including the cost or reminder when present.
# Never concatenate a translated part with a discarded unknown clause.
EXACT = {
    "Draw a card.":"카드 1장을 뽑는다.",
    "【AUTO】 When this card is placed on the stage from your hand, you may put the top card of your clock into your waiting room.":
       "【자동】이 카드가 패에서 무대에 놓였을 때, 자신의 클락 맨 위 카드 1장을 대기실에 놓아도 된다.",
    "【CONT】 This card cannot side attack.":"【지속】이 카드는 사이드 어택을 할 수 없다.",
    "【AUTO】 When this card is placed on the stage from your hand, look at the top card of your deck, and put it on the top of your deck or into your waiting room.":
       "【자동】이 카드가 패에서 무대에 놓였을 때, 자신의 덱 맨 위 카드 1장을 보고 덱 맨 위 또는 대기실에 놓는다.",
    "【AUTO】 When this card is placed on the stage from your hand, look at the top card of your deck, and put it on the top or at the bottom of your deck.":
       "【자동】이 카드가 패에서 무대에 놓였을 때, 자신의 덱 맨 위 카드 1장을 보고 덱 맨 위 또는 맨 아래에 놓는다.",
    "【AUTO】 When this card is placed on the stage from your hand, you may choose 1 card in your hand, and put it into your stock.":
       "【자동】이 카드가 패에서 무대에 놓였을 때, 자신의 패에서 카드 1장을 골라 스톡에 놓아도 된다.",
    "【AUTO】 [Put 1 card from your hand into your waiting room] When this card is placed on the stage from your hand, you may pay the cost. If you do, put the top card of your clock into your stock.":
       "【자동】[패에서 카드 1장을 대기실에 놓는다] 이 카드가 패에서 무대에 놓였을 때, 비용을 지불해도 된다. 지불했다면 자신의 클락 맨 위 카드 1장을 스톡에 놓는다.",
    "【AUTO】 [(1) Put 1 climax from your hand into your waiting room] When this card is placed on the stage from your hand, you may pay the cost. If you do, choose 1 climax in your waiting room, and return it to your hand.":
       "【자동】[(1) 패에서 클라이맥스 1장을 대기실에 놓는다] 이 카드가 패에서 무대에 놓였을 때, 비용을 지불해도 된다. 지불했다면 자신의 대기실에서 클라이맥스 1장을 골라 패로 되돌린다.",
    "【AUTO】 [(1)] When this card attacks, you may pay the cost. If you do, during that attack, perform a trigger check 2 times on the trigger step.":
       "【자동】[(1)] 이 카드가 어택할 때, 비용을 지불해도 된다. 지불했다면 이 어택의 트리거 스텝에 트리거 체크를 2번 한다.",
    "【ACT】 Brainstorm [(1) 【REST】 this card] Flip over 4 cards from the top of your deck, and put them into your waiting room. For each climax revealed among those cards, choose up to 1 character in your waiting room, and return it to your hand.":
       "【기동】집중 [(1) 이 카드를 레스트한다] 자신의 덱 맨 위에서 4장을 뒤집어 대기실에 놓는다. 그중 공개된 클라이맥스 1장당 자신의 대기실에서 캐릭터를 최대 1장 골라 패로 되돌린다.",
    "【ACT】 Brainstorm [(1) 【REST】 this card] Flip over 5 cards from the top of your deck, and put them into your waiting room. For each climax revealed among those cards, draw up to 1 card.":
       "【기동】집중 [(1) 이 카드를 레스트한다] 자신의 덱 맨 위에서 5장을 뒤집어 대기실에 놓는다. 그중 공개된 클라이맥스 1장당 카드를 최대 1장 뽑는다.",
    "【CONT】 You can put any number of cards with the same card name as this card into your deck.":
       "【지속】이 카드와 같은 이름의 카드를 원하는 장수만큼 덱에 넣을 수 있다.",
    "Put this card into your memory.":"이 카드를 자신의 추억에 놓는다.",
    "【AUTO】When this card is placed on your climax area from your hand, perform the【STANDBY】effect.":
       "【자동】이 카드가 패에서 자신의 클라이맥스 영역에 놓였을 때, 스탠바이 효과를 처리한다.",
    "(【GATE】: When this card triggers, you may choose 1 climax in your waiting room, and return it to your hand)":
       "(게이트: 이 카드가 트리거됐을 때, 자신의 대기실에서 클라이맥스 1장을 골라 패로 되돌려도 된다.)",
    "(【TREASURE】: When this card triggers, return this card to your hand. You may put the top card of your deck into your stock)":
       "(트레저: 이 카드가 트리거됐을 때, 이 카드를 패로 되돌린다. 자신의 덱 맨 위 카드 1장을 스톡에 놓아도 된다.)",
    "(【COMEBACK】: When this card triggers, you may choose 1 character in your waiting room, and return it to your hand)":
       "(컴백: 이 카드가 트리거됐을 때, 자신의 대기실에서 캐릭터 1장을 골라 패로 되돌려도 된다.)",
    "(【CHOICE】: When this card triggers, you may choose a character with 【SOUL】 in its trigger icon in your waiting room, and return it to your hand or put it into your stock)":
       "(초이스: 이 카드가 트리거됐을 때, 자신의 대기실에서 트리거 아이콘에 소울이 있는 캐릭터 1장을 골라 패로 되돌리거나 스톡에 놓아도 된다.)",
    "(【STANDBY】: When this card triggers, you may choose 1 character with a level equal to or less than your level +1 in your waiting room, and put it on any position of your stage as【REST】)":
       "(스탠바이: 이 카드가 트리거됐을 때, 자신의 대기실에서 레벨이 자신의 레벨 +1 이하인 캐릭터 1장을 골라 무대의 원하는 칸에 레스트 상태로 놓아도 된다.)",
    "(【DRAW】: When this card triggers, you may draw 1 card)":
       "(드로: 이 카드가 트리거됐을 때, 카드 1장을 뽑아도 된다.)",
    "(【RETURN】: When this card triggers, you may choose 1 of your opponent's characters, and return it to his or her hand)":
       "(리턴: 이 카드가 트리거됐을 때, 상대 캐릭터 1장을 골라 상대의 패로 되돌려도 된다.)",
    "(【SHOT】: During this turn, when the next damage dealt by the attacking character that triggered this card is canceled, deal 1 damage to your opponent)":
       "(샷: 이 턴에 이 카드를 트리거한 공격 캐릭터가 다음에 주는 데미지가 취소되면, 상대에게 데미지 1을 준다.)",
    "(【POOL】: When this card triggers, you may put the top card of your deck into your stock)":
       "(풀: 이 카드가 트리거됐을 때, 자신의 덱 맨 위 카드 1장을 스톡에 놓아도 된다.)",
    "【CONT】 Assist All of your characters in front of this card get +X power. X is equal to that character's level ×500.":
       "【지속】응원: 이 카드 앞의 자신의 모든 캐릭터는 파워 +X를 얻는다. X는 해당 캐릭터의 레벨 ×500이다.",
    "【CONT】 Assist All of your characters in front of this card get +X power. X is equal to 500 multiplied by that character's level.":
       "【지속】응원: 이 카드 앞의 자신의 모든 캐릭터는 파워 +X를 얻는다. X는 500 × 해당 캐릭터의 레벨이다.",
}

PATTERNS = tuple((re.compile(pattern), ko) for pattern, ko in (
    (r"【CONT】 All of your characters get (\+\d+) power and (\+\d+) soul\.", "【지속】자신의 모든 캐릭터는 파워 {0}, 소울 {1}을 얻는다."),
    (r"【CONT】 All of your characters get (\+\d+) soul\.", "【지속】자신의 모든 캐릭터는 소울 {0}을 얻는다."),
    (r"【CONT】 Assist All of your characters in front of this card get (\+\d+) power\.", "【지속】응원: 이 카드 앞의 자신의 모든 캐릭터는 파워 {0}을 얻는다."),
    (r"【CONT】 During your turn, this card gets (\+\d+) power\.", "【지속】자신의 턴 동안 이 카드는 파워 {0}을 얻는다."),
    (r"【AUTO】 When this card is placed on the stage from your hand, this card gets (\+\d+) power until end of turn\.",
     "【자동】이 카드가 패에서 무대에 놓였을 때, 턴 종료 시까지 이 카드는 파워 {0}을 얻는다."),
    (r"【CONT】 If your waiting room has (\d+) or less climax, this card gets (-\d+) level while in your hand\.",
     "【지속】자신의 대기실에 클라이맥스가 {0}장 이하면, 패에 있는 이 카드에 레벨 {1}을 적용한다."),
    (r"【CONT】 Assist All of your level (\d+) or higher characters in front of this card get (\+\d+) power\.",
     "【지속】응원: 이 카드 앞에 있는 레벨 {0} 이상의 자신의 모든 캐릭터는 파워 {1}을 얻는다."),
    (r"【AUTO】 When this card becomes 【REVERSE】, if this card's battle opponent is level (\d+) or lower, you may 【REVERSE】 that character\.",
     "【자동】이 카드가 리버스됐을 때, 이 카드의 배틀 상대가 레벨 {0} 이하면 그 캐릭터를 리버스해도 된다."),
    (r"【CONT】 If your stock has (\d+) or less cards, this card gets (\+\d+) power\.",
     "【지속】자신의 스톡이 {0}장 이하면 이 카드는 파워 {1}을 얻는다."),
    (r"【AUTO】 When this card attacks, if the character facing this card is level (\d+) or higher, this card gets (\+\d+) power until end of turn\.",
     "【자동】이 카드가 어택할 때, 정면의 캐릭터가 레벨 {0} 이상이면 턴 종료 시까지 이 카드는 파워 {1}을 얻는다."),
    (r"【CONT】 Memory During your turn, if you have a card in your memory, this card gets (\+\d+) power\.",
     "【지속】기억: 자신의 턴 동안 자신의 추억에 카드가 있으면 이 카드는 파워 {0}을 얻는다."),
    (r"【AUTO】 When this card is placed on the stage from your hand, choose 1 of your characters, and that character gets (\+\d+) soul until end of turn\.",
     "【자동】이 카드가 패에서 무대에 놓였을 때, 자신의 캐릭터 1장을 고른다. 턴 종료 시까지 그 캐릭터는 소울 {0}을 얻는다."),
))
BACKUP = re.compile(r"【ACT】 【COUNTER】 Backup (\d+), Level (\d+) \[(?:\((\d+)\) )?Put this card from your hand into your waiting room\] \(Choose (?:1|one) of your characters that is being frontal attacked, and that character gets \+(\d+) power until end of turn\)")
ENCORE = re.compile(r"【AUTO】 Encore \[(Put (?:1|a) character from your hand into your waiting room|Put the top card of your deck into your clock)\] \(When this card is put into your waiting room from the stage, you may pay the cost\. If you do, return this card to its previous stage position as 【REST】\)")


def rule_line(line):
    line = " ".join(line.split())
    if line in EXACT:
        return EXACT[line]
    for pattern, wording in PATTERNS:
        match = pattern.fullmatch(line)
        if match:
            return wording.format(*match.groups())
    match = BACKUP.fullmatch(line)
    if match and match[1] == match[4]:
        cost = f"({match[3]}) " if match[3] is not None else ""
        return (f"【기동】【카운터】백업 {match[1]}, 레벨 {match[2]} "
                f"[{cost}이 카드를 패에서 대기실에 놓는다] "
                f"(프런트 어택을 받고 있는 자신의 캐릭터 1장을 고른다. 턴 종료 시까지 그 캐릭터는 파워 +{match[4]}을 얻는다.)")
    match = ENCORE.fullmatch(line)
    if match:
        cost = "자신의 덱 맨 위 카드 1장을 클락에 놓는다" if "deck" in match[1] else "패의 캐릭터 1장을 대기실에 놓는다"
        return (f"【자동】앙코르 [{cost}] (이 카드가 무대에서 자신의 대기실에 놓였을 때, 비용을 지불해도 된다. "
                "지불했다면 이 카드를 무대의 원래 칸에 레스트 상태로 되돌린다.)")
    return translate_ability(line, TRAITS)


def complete_effect(effect):
    if not effect:
        return None
    lines = [rule_line(line) for line in effect.splitlines() if line.strip()]
    return "\n".join(lines) if lines and all(lines) else None


# Only names/titles whose reading is the same throughout the stated product family.
PEOPLE = {
    "5HY": {"Ichika Nakano":"나카노 이치카","Nino Nakano":"나카노 니노","Miku Nakano":"나카노 미쿠",
            "Yotsuba Nakano":"나카노 요츠바","Itsuki Nakano":"나카노 이츠키","Futaro Uesugi":"우에스기 후타로"},
    "NIK": {"Rapi":"라피","Anis":"아니스","Modernia":"모더니아","Dorothy":"도로시","Marian":"마리안",
            "Ludmilla":"루드밀라","Scarlet":"홍련","Snow White":"스노우 화이트","Rapunzel":"라푼젤",
            "Alice":"앨리스","Blanc":"블랑","Noir":"누아르","Naga":"나가","Tia":"티아","Emma":"엠마"},
    "SAO":{"Asuna":"아스나","Kirito":"키리토","Sinon":"시논","Alice":"앨리스","Yui":"유이","Eugeo":"유지오"},
    "RZ":{"Emilia":"에밀리아","Rem":"렘","Ram":"람","Beatrice":"베아트리스"},
    "SBY":{"Mai Sakurajima":"사쿠라지마 마이","Kaede Azusagawa":"아즈사가와 카에데",
           "Shoko Makinohara":"마키노하라 쇼코","Rio Futaba":"후타바 리오"},
    "SHS":{"Megumi":"메구미","Eriri":"에리리","Utaha":"우타하","Michiru":"미치루","Izumi":"이즈미"},
    "LRC":{"Takina":"타키나","Chisato":"치사토"},
}
TITLE_PHRASES = {
    "Unparalleled Beauty":"비할 데 없는 아름다움", "Irrepressible Feelings":"억누를 수 없는 마음",
    "Relaxing in a Yukata":"유카타 차림의 휴식", "Flowers of Gratitude":"감사의 꽃", "Beside You":"네 곁에서",
    "Guts of the Eldest Sister":"맏언니의 배짱", "The Answer He Chose":"그가 선택한 대답",
    "Established Actress":"인정받는 배우", "Sneaking Into the School Festival":"학교 축제에 몰래 들어가기",
    "Our Resolve":"우리의 결심","Unexpected Meeting":"뜻밖의 만남","First Date":"첫 데이트",
    "The Quintuplets After 5 Years":"5년 후의 다섯 쌍둥이","Intimate Sisters":"사이좋은 자매",
    "Good at Trapping People":"사람을 함정에 빠뜨리는 데 능숙한","Reminiscing":"추억에 잠긴",
    "Quintuplicate Trails":"다섯 쌍둥이의 발자취",
    "A New Start":"새로운 시작","A New Story":"새로운 이야기","Pajama Party":"파자마 파티",
    "Summer Festival":"여름 축제","Battle Stance":"전투 태세","First Job":"첫 일","Transfer Student":"전학생",
    "Taking a Break":"잠깐의 휴식","In a Yukata":"유카타 차림","Happy New Year":"새해 복 많이 받으세요",
    "Student Council President":"학생회장","Swimsuit":"수영복","Cat Ears":"고양이 귀","New Year":"새해",
}


def literal_title(name, family):
    names = people_for(family)
    if name in names:
        return names[name]
    parts=title_with_people(name,family)
    if parts:
        title, people=parts
        if not title:
            return people
        if title in TITLE_PHRASES:
            return TITLE_PHRASES[title]+", "+people
    return None


@lru_cache(maxsize=256)
def people_for(family):
    return {**PEOPLE.get(family,{}),**names_for(family)}


@lru_cache(maxsize=512)
def title_with_people(name, family):
    """Return the original title and a suffix made entirely of scoped, known person names."""
    names=people_for(family)
    if not names:
        return None
    cuts=[0]+[m.end() for m in re.finditer(", ",name)]
    for start in cuts:
        original=re.split(r", (?:and |& )?| & | and ",name[start:])
        if all(part in names for part in original):
            return name[:start].removesuffix(", "), " · ".join(names[part] for part in original)
    return None
RULE_MARKERS = {"AUTO":"자동","CONT":"지속","ACT":"기동","COUNTER":"카운터","CXCOMBO":"CX 콤보",
                "REST":"레스트","REVERSE":"리버스","STAND":"스탠드","CLOCK":"클락","REPLAY":"리플레이",
                "1/TURN":"턴당 1회",**TRIGGERS}
RULE_WORDS = {
    "waiting room":"대기실","climax area":"클라이맥스 영역","center stage":"중앙 무대",
    "back stage":"후열","stock":"스톡","climax":"클라이맥스","clock":"클락","deck":"덱",
    "hand":"패","memory":"추억","encore":"앙코르","soul":"소울","power":"파워",
    "turn":"턴","level":"레벨","stage":"무대","character":"캐릭터","characters":"캐릭터",
    "at the beginning of":"시작 시","until end of turn":"턴 종료 시까지",
}
_NUMBER = re.compile(r"[+\-]?\d+(?:[.,]\d+)*%?")
_HANGUL = re.compile(r"[가-힣]")


def draft_line(model, kind, source, family):
    """Translate one complete English unit. Return None on loss of a token or conditional."""
    if not source or len(source) > (320 if kind == "name" else 1800) or source.strip() in {"-", "?", "N/A"}:
        return None
    if kind == "rule":
        exact = rule_line(source)
        if exact:
            return exact
        return rule_draft(model,source,RULE_MARKERS,TRAITS)
    terms = {**PEOPLE.get(family, {}), **{row["english"]: row["korean"] for row in character_references(source, family)}}
    if source in terms:
        return terms[source]
    markers = {}

    def protect(m):
        marker = str(85127000+len(markers))
        if marker in source:
            raise ValueError("Reserved source marker")
        markers[marker] = terms[m.group()] if m.group() in terms else terms[m.group().lower()]
        return " "+marker+" "

    # Proper names must match case and word boundaries. The English rule lexicon also accepts
    # ordinary sentence-initial capitalization without changing a similarly named character.
    words = [re.escape(t) if t.startswith("【") else r"(?<![A-Za-z])"+re.escape(t)+r"(?![A-Za-z])"
             for t in sorted(terms,key=len,reverse=True)]
    protected = re.sub("|".join(words),protect,source,flags=re.I if kind=="rule" else 0) if words else source
    value = model().translate(protected.strip(),"en","ko")
    if not value or re.search(r"[ぁ-ヿ一-鿿]",value) or not _HANGUL.search(value):
        return None
    if Counter(_NUMBER.findall(protected)) != Counter(_NUMBER.findall(value)):
        return None
    for marker, reading in markers.items():
        if value.count(marker)!=1:
            return None
        value = value.replace(marker,reading)
    if re.search(r"[A-Za-z]{3,}", value) or len(value) > (320 if kind=="name" else 2200):
        return None
    return value.strip()
