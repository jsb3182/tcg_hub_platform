"""Translate complete Weiss abilities one clause at a time, preserving their printed structure."""
from collections import Counter
import re


WORDS = dict(zip("zero one two three four five six seven eight nine ten".split(), map(str, range(11))))
NUMBERS = re.compile(r"[+−-]?\d+(?:[.,]\d+)*%?|[+−-]?\bX\b")
WORD_NUMBER = re.compile(r"\b(" + "|".join(WORDS) + r")\b", re.I)
HANGUL = re.compile(r"[가-힣]")

# Type/name identifiers remain verbatim unless a Korean term for this exact token is known.
# A quoted ability is parsed recursively as rules, while a quoted card title is an identifier.
ATOMS = re.compile(r'【([^【】]+)】|《([^《》]+)》|["“]([^"“”\r\n]+)["”]|(\d+[.,]\d+)|([,.;!?()\[\]［］])')
EXACT = {
    "if you do":"그렇게 했다면", "if you do not":"그렇게 하지 않았다면",
    "you may pay the cost":"비용을 지불해도 된다", "when this card attacks":"이 카드가 어택할 때",
    "when this card is placed on the stage from your hand":"이 카드가 패에서 무대에 놓였을 때",
    "when this card is placed on stage from your hand":"이 카드가 패에서 무대에 놓였을 때",
    "when this card is put into your waiting room from the stage":"이 카드가 무대에서 자신의 대기실에 놓였을 때",
    "when this card is placed on your climax area from your hand":"이 카드가 패에서 자신의 클라이맥스 영역에 놓였을 때",
    "when your climax is placed on your climax area":"자신의 클라이맥스가 자신의 클라이맥스 영역에 놓였을 때",
    "when a climax is placed on your climax area":"클라이맥스가 자신의 클라이맥스 영역에 놓였을 때",
    "put it on the top of your deck":"그 카드를 자신의 덱 맨 위에 놓는다",
    "put them on the top of your deck in any order":"그 카드들을 원하는 순서로 자신의 덱 맨 위에 놓는다",
    "put it in any position of your stage":"그 카드를 자신의 무대에서 원하는 칸에 놓는다",
    "at the end of the turn":"턴 종료 시", "put that character into your memory":"그 캐릭터를 자신의 추억에 놓는다",
    "put it into your hand":"그 카드를 자신의 패에 넣는다", "return it to your hand":"그 카드를 자신의 패로 되돌린다",
    "put them into your hand":"그 카드들을 자신의 패에 넣는다", "put it into your stock":"그 카드를 자신의 스톡에 놓는다",
    "put this card into your memory":"이 카드를 자신의 추억에 놓는다",
    "put this card into your waiting room":"이 카드를 자신의 대기실에 놓는다",
    "put the rest into your waiting room":"나머지를 자신의 대기실에 놓는다",
    "put it into your waiting room":"그 카드를 자신의 대기실에 놓는다",
    "put them into your waiting room":"그 카드들을 자신의 대기실에 놓는다",
    "return it to its original place":"원래 장소로 되돌린다",
    "return the revealed card to its original place":"공개한 카드를 원래 장소로 되돌린다",
    "reveal it to your opponent":"그 카드를 상대에게 공개한다", "reveal them to your opponent":"그 카드들을 상대에게 공개한다",
    "shuffle your deck":"자신의 덱을 섞는다", "shuffle your deck afterwards":"그 후 자신의 덱을 섞는다",
    "look at the top card of your deck":"자신의 덱 맨 위 카드 1장을 본다",
    "reveal the top card of your deck":"자신의 덱 맨 위 카드 1장을 공개한다",
    "put the top card of your deck into your clock":"자신의 덱 맨 위 카드 1장을 클락에 놓는다",
    "you may put the top card of your clock into your waiting room":"자신의 클락 맨 위 카드 1장을 대기실에 놓아도 된다",
    "you may put the top card of your deck into your stock":"자신의 덱 맨 위 카드 1장을 스톡에 놓아도 된다",
    "put that character into your opponent's clock":"그 캐릭터를 상대의 클락에 놓는다",
    "you may put that character into your opponent's stock":"그 캐릭터를 상대의 스톡에 놓아도 된다",
    "you may put that character at the bottom of your opponent's deck":"그 캐릭터를 상대 덱 맨 아래에 놓아도 된다",
    "this damage may be canceled":"이 데미지는 취소될 수 있다", "damage may be canceled":"데미지는 취소될 수 있다",
    "during your turn":"자신의 턴 동안", "during your opponent's turn":"상대의 턴 동안",
    "until end of turn":"턴 종료 시까지", "draw a card":"카드 1장을 뽑는다",
    "at the beginning of your climax phase":"자신의 클라이맥스 페이즈 시작 시",
    "at the beginning of your opponent's attack phase":"상대 어택 페이즈 시작 시",
    "when damage dealt by this card is canceled":"이 카드가 주는 데미지가 취소됐을 때",
    "at the beginning of your encore step":"자신의 앙코르 스텝 시작 시",
    "that character gets the following ability until end of turn":"그 캐릭터는 턴 종료 시까지 다음 능력을 얻는다",
    "this card":"이 카드", "otherwise":"그렇지 않으면", "or":"또는", "and":"그리고",
    "encore":"앙코르", "brainstorm":"집중", "assist":"응원", "change":"체인지",
    "backup":"백업", "alarm":"알람", "memory":"기억", "experience":"경험", "in battle":"배틀 중",
}
FORMS = [(re.compile(pattern), result) for pattern, result in (
    (r"put (\d+|a|one) (card|character|climax)s? from your hand into your waiting room", "자신의 패에서 {1} {0}장을 대기실에 놓는다"),
    (r"choose (\d+) of your characters", "자신의 캐릭터 {0}장을 고른다"),
    (r"choose (\d+) of your opponent's characters", "상대의 캐릭터 {0}장을 고른다"),
    (r"choose (\d+) cards? in your hand", "자신의 패에서 카드 {0}장을 고른다"),
    (r"choose (\d+) cards? from among them", "그중 카드 {0}장을 고른다"),
    (r"(this card|that character|all of your characters) gets? ([+−-](?:\d+|x)) (power|soul)( until end of turn)?", "{3}{0} {2} {1}을 얻는다"),
    (r"draw (\d+) cards?", "카드 {0}장을 뽑는다"), (r"draw up to (\d+) cards?", "카드를 최대 {0}장 뽑는다"),
    (r"deal (\d+) damage to your opponent", "상대에게 데미지 {0}을 준다"),
    (r"put the top (\d+) cards? of your deck into your waiting room", "자신의 덱 맨 위 {0}장을 대기실에 놓는다"),
    (r"look at up to (\d+) cards? from the top of your deck", "자신의 덱 맨 위에서 최대 {0}장을 본다"),
    (r"if that card is level (\d+) or higher", "그 카드가 레벨 {0} 이상이라면"),
    (r"flip over (\d+) cards? from the top of your deck", "자신의 덱 맨 위에서 {0}장을 뒤집는다"),
)]
ARGS = {"a":"1", "one":"1", "card":"카드", "character":"캐릭터", "climax":"클라이맥스",
        "this card":"이 카드는", "that character":"그 캐릭터는", "all of your characters":"자신의 모든 캐릭터는",
        "power":"파워", "soul":"소울", " until end of turn":"턴 종료 시까지 ", None:""}
ZONES = {"hand":"패", "waiting room":"대기실", "deck":"덱", "stock":"스톡", "clock":"클락",
         "stage":"무대", "memory":"추억", "climax area":"클라이맥스 영역"}
KO_TERMS = {"대기실":"대기실", "대기 방":"대기실", "대기방":"대기실", "손":"패", "손패":"패", "데크":"덱",
            "스테이지":"무대", "무대":"무대", "기억":"추억", "스톡":"스톡", "시계":"클락",
            "클라이막스":"클라이맥스", "반대자":"상대", "상대방":"상대"}
GAME_TERMS = {**ZONES, "back stage":"후열", "center stage":"중앙 무대", "climax":"클라이맥스",
              "power":"파워", "soul":"소울", "level":"레벨", "cost":"비용", "turn":"턴", "character":"캐릭터",
              "characters":"캐릭터", "encore":"앙코르", "brainstorm":"집중", "marker":"마커", "markers":"마커",
              "opponent":"상대", "opponent's":"상대의", "opponent’s":"상대의"}
TERM_PATTERN = re.compile(r"\b(?:"+"|".join(map(re.escape,sorted(GAME_TERMS,key=len,reverse=True)))+r")\b",re.I)

# A covered clause can still be read if the model drops a cost, zone, or number.
# These are source-order glosses, explicitly labeled at display time. Never invent a
# translation for an unknown word, and preserve card/trait placeholders verbatim.
GLOSS = {
    **GAME_TERMS, "choose":"선택", "chooses":"선택", "up to":"최대", "look at":"보기",
    "equal to or lower than":"이하", "equal to or higher than":"이상", "equal to or less than":"이하",
    "or less":"이하", "or lower":"이하", "or fewer":"이하", "or higher":"이상", "or more":"이상",
    "more than":"초과", "less than":"미만", "higher than":"보다 높음", "lower than":"보다 낮음",
    "equal to":"같음", "at least":"적어도", "as many as":"같은 수만큼", "as long as":"하는 동안",
    "put":"놓기", "place":"놓기", "is placed":"놓임", "was placed":"놓였음",
    "is put":"놓임", "are put":"놓임", "to its previous stage position":"도착지: 무대의 원래 칸",
    "back to":"되돌릴 곳", "from":"출발지", "into":"도착지", "onto":"도착지", "to":"대상·도착지",
    "on the top of":"맨 위에", "at the bottom of":"맨 아래에", "on the bottom of":"맨 아래에",
    "the top card of":"맨 위 카드", "the top":"맨 위", "the bottom":"맨 아래",
    "from among them":"그중에서", "from among those cards":"그 카드 중에서",
    "among those cards":"그 카드 중", "among them":"그중", "at random":"무작위로",
    "in any order":"원하는 순서로", "in the order of your choice":"원하는 순서로",
    "in any position of":"원하는 칸에", "in the middle position of":"가운데 칸에",
    "on any position of":"원하는 칸에", "any position":"원하는 칸", "face up":"앞면으로",
    "face down":"뒷면으로", "face-up":"앞면", "face-down":"뒷면", "underneath":"아래에",
    "return":"되돌리기", "returns":"되돌리기", "draw":"뽑기", "draws":"뽑기",
    "search":"찾기", "searches":"찾기", "shuffle":"섞기", "reveal":"공개", "revealed":"공개한",
    "exchange":"교환", "swap":"교환", "discard":"버리기", "flip over":"뒤집기",
    "deal":"주기", "damage":"데미지", "is canceled":"취소됨", "is not canceled":"취소되지 않음",
    "gets":"얻음", "get":"얻음", "loses":"잃음", "has":"보유", "have":"보유",
    "gain":"얻음", "gains":"얻음", "use":"사용", "when you use":"사용할 때", "pay":"지불",
    "attack":"어택", "attacks":"어택", "front attack":"프런트 어택", "side attack":"사이드 어택",
    "during this turn":"이 턴 동안", "until end of turn":"턴 종료 시까지", "until the end of":"종료 시까지",
    "at the beginning of":"시작 시", "at the end of":"종료 시", "for each":"각각에 대해",
    "the number of":"개수", "number":"수", "any number of":"원하는 수만큼", "times":"회", "time":"회",
    "level":"레벨", "higher":"높음", "lower":"낮음", "all":"모든", "any":"원하는", "each":"각",
    "cards":"카드", "card":"카드", "this card":"이 카드", "that card":"그 카드",
    "those cards":"그 카드들", "other":"다른", "another":"또 다른", "opposite this":"이 카드 정면",
    "with":"함께·조건", "without":"없이", "in its card name":"카드 이름에 포함",
    "in the card name":"카드 이름에 포함", "in their card names":"카드 이름에 포함",
    "with the same name":"같은 이름의", "card named":"해당 이름의 카드", "card name":"카드 이름",
    "the following ability":"다음 능력", "ability":"능력", "abilities":"능력", "effect":"효과",
    "activate":"발동", "activates":"발동", "becomes":"상태가 됨", "become":"상태가 됨",
    "battle opponent":"배틀 상대", "in battle":"배틀 중", "in front of":"앞에", "facing":"정면의",
    "position":"칸", "battle":"배틀", "turns":"턴", "phase":"페이즈", "step":"스텝", "trigger":"트리거",
    "event":"이벤트", "events":"이벤트", "trigger icon":"트리거 아이콘", "icon":"아이콘",
    "does not":"하지 않음", "do not":"하지 않음", "cannot":"할 수 없음", "can't":"할 수 없음",
    "is not":"아님", "not":"아님", "may":"선택 가능", "may not":"하지 않아도 됨", "instead":"대신",
    "if":"조건", "unless":"예외 조건", "when":"시점", "while":"동안", "during":"동안", "before":"이전",
    "after":"이후", "then":"그 후", "and":"그리고", "or":"또는", "both":"둘 다", "except":"제외",
    "either":"둘 중 하나", "this":"이", "that":"그", "these":"이들", "those":"그들",
    "your opponent's":"상대의", "your opponent":"상대", "their":"그들의", "they":"그들",
    "of your":"자신의", "your":"자신의", "you":"자신", "its":"그것의", "it":"그것", "them":"그것들",
    "in":"에 있는", "on":"에", "of":"의", "for":"대상", "by":"통해", "as":"상태로",
    "are":"임", "is":"임", "the":"", "a":"한", "an":"한", "or a":"또는 한",
    "or an":"또는 한", "one":"1", "x":"X", "×":"×",
}
GLOSS_PATTERN = re.compile(r"(?<![\w'])("+"|".join(map(re.escape,sorted(GLOSS,key=len,reverse=True)))+
                           r")(?![\w'])|[+−-]?(?:\d+(?:[.,]\d+)*|X)|[×:;/-]", re.I)


def gloss(chunk):
    text=WORD_NUMBER.sub(lambda m:WORDS[m[0].lower()],chunk).strip()
    if re.search(r"\bmay not\b",text,re.I):
        return None
    terms=[]
    end=0
    for m in GLOSS_PATTERN.finditer(text):
        if text[end:m.start()].strip():
            return None
        value=GLOSS[m[1].lower()] if m[1] else m[0]
        if value:
            terms.append(value)
        end=m.end()
    if not terms or text[end:].strip() or not any(HANGUL.search(t) for t in terms):
        return None
    return "〔영문 어순 풀이: "+" · ".join(terms)+"〕"


def wording(text):
    key = WORD_NUMBER.sub(lambda m: WORDS[m[0].lower()], text.casefold().strip())
    key = key.removeprefix("and ") if len(key)>4 else key
    if key in EXACT:
        return EXACT[key]
    for pattern, fmt in FORMS:
        match = pattern.fullmatch(key)
        if match:
            return fmt.format(*(ARGS.get(s, s.upper() if s and s.endswith("x") else s) for s in match.groups()))
    return None


def translated_clause(model, chunk):
    chunk = chunk.strip()
    if not chunk:
        return ""
    fixed = wording(chunk)
    if fixed:
        return fixed
    if not re.search("[A-Za-z]",chunk):
        return chunk if re.fullmatch(r"[\d\s+×%:−/.-]+",chunk) else None
    english = WORD_NUMBER.sub(lambda m: WORDS[m[0].lower()], chunk)
    terms = {}
    def protect(m):
        token = str(68142000 + len(terms))
        terms[token] = GAME_TERMS[m[0].lower()]
        return " "+token+" "
    protected = TERM_PATTERN.sub(protect,english)
    ko = model().translate(protected, "en", "ko")
    if not ko or not HANGUL.search(ko) or re.search(r"[ぁ-ヿ一-鿿]", ko):
        return None
    if Counter(NUMBERS.findall(protected)) != Counter(NUMBERS.findall(ko)):
        return None
    for token, korean in terms.items():
        if ko.count(token)!=1:
            return None
        ko=ko.replace(token,korean)
    ko=ko.removesuffix(".").strip().replace("귀하의","자신의").replace("당신의","자신의")
    # The original owner and both ends of a transfer must survive. In particular, the model
    # sometimes produces "무대에서 패로" for "from your hand onto the stage".
    for zone, word in ZONES.items():
        if not re.search(r"\b" + zone + r"\b", english, re.I):
            continue
        for alt,new in KO_TERMS.items():
            if word in new and alt!=new:
                ko=re.sub(r"(?<![가-힣])"+re.escape(alt)+r"(?=$|[\s.,]|에서|으로|로|에|을|를|이|가|의)",new,ko)
        if re.search(r"\bfrom (?:your |the |its |their |your opponent's )?"+zone+r"\b",english,re.I):
            if not re.search(word+r"(?:에서|으로부터|로부터)",ko):
                return None
        if re.search(r"\b(?:into|onto|to) (?:your |the |its |their |your opponent's )?"+zone+r"\b",english,re.I):
            if not re.search(word+r"(?:으로|로|에(?!서))",ko):
                return None
    for en, expected in ((r"\bmay\b",r"해도|어도|아도|여도|수 있|수도 있"),
                         (r"\b(?:cannot|can't|do not|does not)\b",r"않|없|못|금지"),
                         (r"\bup to\b",r"최대|까지|이하"), (r"\bopponent",r"상대|적의"),
                         (r"\bif\b",r"면|경우|때|다면|라면")):
        if re.search(en,english,re.I) and not re.search(expected,ko):
            return None
    if re.search(r"[a-zA-Z]{4,}", ko):
        return None
    return ko.strip()


def rule_draft(model, source, markers, traits):
    # Protect entities as indivisible values inside clauses, so the model can put the noun
    # in its Korean grammatical position. Icons, punctuation, costs, and effects stay separate.
    saved = {}
    fragments = []
    pending = []
    valid = True

    def flush():
        nonlocal valid
        raw = "".join(pending).strip()
        if raw:
            literals = {}
            def mark(m):
                token = str(75162000 + len(literals))
                if token in raw:
                    return m[0]
                literals[token] = saved[m[0]]
                return " " + token + " "
            protected = re.sub("¤[0-9]+¤", mark, raw)
            value = translated_clause(model, protected)
            if value is None:
                value = gloss(protected)
            if value is None:
                valid = False
            else:
                for token, literal in literals.items():
                    if value.count(token)!=1:
                        valid = False
                    value=value.replace(token,literal)
                fragments.append(value)
        pending.clear()

    prev = 0
    for m in ATOMS.finditer(source):
        pending.append(source[prev:m.start()])
        prev=m.end()
        icon,trait,title,decimal,punct=m.groups()
        if decimal:
            pending.append(decimal)
        elif trait or (title and not re.search(r"【|^(?:This card (?:gets|cannot)|When this card|Choose \d|Put \d)", title, re.I)):
            token = f"¤{len(saved)}¤"
            saved[token]="《"+traits.get(trait,trait)+"》" if trait else "“"+title+"”"
            pending.append(token)
        else:
            flush()
            if icon:
                val=markers.get(icon.upper().replace(" ",""),icon)
                fragments.append("【"+val+"】")
            elif title:
                nested=rule_draft(model,title,markers,traits)
                valid &= nested is not None
                fragments.append("“"+(nested or "")+"”")
            else:
                fragments.append(punct)
    pending.append(source[prev:])
    flush()
    rendered = " ".join(fragments)
    rendered = re.sub(r"\s+([,.;!?)\]］])",r"\1", rendered)
    rendered = re.sub(r"([(\[［])\s+",r"\1",rendered)
    if not valid or len(rendered)>2200 or not HANGUL.search(rendered):
        return None
    return rendered
