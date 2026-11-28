"""Full-line wording for recurring English Weiß Schwarz abilities."""
import re


# Literal text is escaped. Only numbers and printed trait names vary within these abilities.
FORMS = [
    ("【CONT】 This card gets +{power} power for each of your other {traits} characters.",
     "【지속】자신의 다른 {traits} 캐릭터 1장당 이 카드는 파워 +{power}을 얻는다."),
    ("【CONT】 If you have {n} or more other {traits} characters, this card gets +{power} power.",
     "【지속】자신의 다른 {traits} 캐릭터가 {n}장 이상이라면 이 카드는 파워 +{power}을 얻는다."),
    ("【CONT】 All of your other {traits} characters get +{power} power.",
     "【지속】자신의 다른 모든 {traits} 캐릭터는 파워 +{power}을 얻는다."),
    ("【CONT】 If you have {n} or more {traits} characters, this card gets -{level} level while in your hand.",
     "【지속】자신의 {traits} 캐릭터가 {n}장 이상이라면 패에 있는 이 카드의 레벨은 {level} 낮아진다."),
    ("【CONT】 If all of your characters are {traits}, this card gets +{power} power.",
     "【지속】자신의 캐릭터가 모두 {traits}라면 이 카드는 파워 +{power}을 얻는다."),
    ("【CONT】 During your turn, this card gets +{power} power for each of your other {traits} characters.",
     "【지속】자신의 턴 동안 자신의 다른 {traits} 캐릭터 1장당 이 카드는 파워 +{power}을 얻는다."),
    ("【CONT】 During your turn, if you have another {traits} character, this card gets +{power} power.",
     "【지속】자신의 턴 동안 자신의 다른 {traits} 캐릭터가 있다면 이 카드는 파워 +{power}을 얻는다."),
    ("【CONT】 Assist All of your {traits} characters in front of this card get +X power. X is equal to that character's level ×{multiplier}.",
     "【지속】응원. 이 카드 앞에 있는 자신의 모든 {traits} 캐릭터는 파워 +X를 얻는다. X는 해당 캐릭터의 레벨 ×{multiplier}이다."),
    ("【CONT】 This card gets +{power} power for each other {traits} character in your back stage.",
     "【지속】자신의 후열에 있는 다른 {traits} 캐릭터 1장당 이 카드는 파워 +{power}을 얻는다."),
    ("【CONT】 If there is a marker underneath this card, this card gets +{power} power.",
     "【지속】이 카드 아래에 마커가 있다면 이 카드는 파워 +{power}을 얻는다."),
    ('【CONT】 All of your opponent\'s characters get "【AUTO】 Encore [({cost})]".',
     "【지속】상대의 모든 캐릭터는 「【자동】앙코르 [({cost})]」를 얻는다."),
    ("【AUTO】 When your other {traits} character attacks, this card gets +{power} power until end of turn.",
     "【자동】자신의 다른 {traits} 캐릭터가 어택했을 때, 턴 종료 시까지 이 카드는 파워 +{power}을 얻는다."),
    ("【AUTO】 When another of your characters becomes 【REVERSE】 in battle, this card gets +{power} power until end of turn.",
     "【자동】자신의 다른 캐릭터가 배틀 중 리버스 상태가 되었을 때, 턴 종료 시까지 이 카드는 파워 +{power}을 얻는다."),
    ("【AUTO】 When this card attacks, choose 1 of your {traits} characters, and that character gets +{power} power until end of turn.",
     "【자동】이 카드가 어택했을 때, 자신의 {traits} 캐릭터 1장을 고른다. 턴 종료 시까지 그 캐릭터는 파워 +{power}을 얻는다."),
    ("【AUTO】 When this card attacks, choose 1 of your characters, and that character gets +{power} power until end of turn.",
     "【자동】이 카드가 어택했을 때, 자신의 캐릭터 1장을 고른다. 턴 종료 시까지 그 캐릭터는 파워 +{power}을 얻는다."),
    ("【AUTO】 When this card attacks, this card gets +X power until end of turn. X is equal to the number of other {traits} characters you have ×{multiplier}.",
     "【자동】이 카드가 어택했을 때, 턴 종료 시까지 이 카드는 파워 +X를 얻는다. X는 자신의 다른 {traits} 캐릭터 수 ×{multiplier}이다."),
    ("【AUTO】 When this card is placed on the stage from your hand, this card gets +X power until end of turn. X is equal to the number of {traits} characters you have ×{multiplier}.",
     "【자동】이 카드가 패에서 무대에 놓였을 때, 턴 종료 시까지 이 카드는 파워 +X를 얻는다. X는 자신의 {traits} 캐릭터 수 ×{multiplier}이다."),
    ("【AUTO】 [({cost})] At the beginning of the encore step, if you do not have another 【REST】 character in your center stage, you may pay the cost. If you do, 【REST】 this card.",
     "【자동】[({cost})] 앙코르 스텝 시작에 자신의 전열에 다른 레스트 상태의 캐릭터가 없다면 비용을 지불해도 된다. 지불했다면 이 카드를 레스트한다."),
    ("【AUTO】 When this card is placed on the stage from your hand, look at up to {n} cards from the top of your deck, and put them on the top of your deck in any order.",
     "【자동】이 카드가 패에서 무대에 놓였을 때, 자신의 덱 위에서 카드를 최대 {n}장 보고 원하는 순서로 덱 위에 놓는다."),
    ("【AUTO】 When this card is placed on the stage from your hand, look at up to {n} cards from the top of your deck, choose up to 1 card from among them, put it into your hand, and put the rest into your waiting room.",
     "【자동】이 카드가 패에서 무대에 놓였을 때, 자신의 덱 위에서 카드를 최대 {n}장 본다. 그중 최대 1장을 골라 패에 넣고 나머지는 대기실에 놓는다."),
    ("【ACT】 [【REST】 this card] Choose 1 of your {traits} characters, and that character gets +{power} power until end of turn.",
     "【기동】[이 카드를 레스트한다] 자신의 {traits} 캐릭터 1장을 고른다. 턴 종료 시까지 그 캐릭터는 파워 +{power}을 얻는다."),
    ("【ACT】 [【REST】 this card] Choose 1 of your characters, and that character gets +{power} power until end of turn.",
     "【기동】[이 카드를 레스트한다] 자신의 캐릭터 1장을 고른다. 턴 종료 시까지 그 캐릭터는 파워 +{power}을 얻는다."),
]


def compile_form(form):
    tokens = re.split(r"(\{[a-z]+\})", form)
    expression = []
    for token in tokens:
        if token == "{traits}":
            expression.append(r"(?P<traits>《[^《》]+》(?: or 《[^《》]+》)?)")
        elif token.startswith("{"):
            expression.append(r"(?P<" + token[1:-1] + r">[0-9]+)")
        else:
            expression.append(re.escape(token))
    return re.compile("".join(expression))


MATCHERS = [(compile_form(english), korean) for english, korean in FORMS]


def translate_ability(line, trait_names):
    for pattern, korean in MATCHERS:
        match = pattern.fullmatch(line)
        if not match:
            continue
        values = match.groupdict()
        if "traits" in values:
            traits = re.findall(r"《([^《》]+)》", values["traits"])
            if any(trait not in trait_names for trait in traits):
                return None
            values["traits"] = " 또는 ".join("《" + trait_names[trait] + "》" for trait in traits)
        return korean.format_map(values)
    return None
