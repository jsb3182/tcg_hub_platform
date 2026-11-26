"""Summarize public timeline facts without mirroring posts or attributing unconfirmed releases to a publisher."""
import re

TOPICS = (
    (r"rumou?r|unconfirmed|leak(?:ed|s)?|유출|미확인|未確認|リーク", "미확인 소식"),
    (r"banlist|ban list|restricted list|forbidden (?:and|&) limited|금제|금지.{0,4}제한|禁止.{0,4}制限", "금제 소식"),
    (r"deck\s*list|deck\s*recipe|입상.?덱|덱.?레시피|デッキ(?:レシピ|リスト)|優勝デッキ", "덱 레시피"),
    (r"reveal|선공개|신규 카드|公開", "카드 공개"),
    (r"release|booster|발매|입고|発売", "발매 소식"),
    (r"tournament|championship|대회|大会", "대회 소식"),
)
FACTS = (
    ("카드 번호", "Card numbers", "カード番号", re.compile(r"\b(?:OP|ST|EB|PRB|BT|EX|SD|P)[0-9]{0,3}-[A-Z]?[0-9]{2,4}\b", re.I)),
    ("날짜", "Dates mentioned", "記載日", re.compile(r"(?<!\d)20\d{2}[-/.年](?:0?[1-9]|1[0-2])[-/.月](?:0?[1-9]|[12]\d|3[01])日?(?!\d)")),
    ("해시태그", "Hashtags", "ハッシュタグ", re.compile(r"(?<!\w)#[^\W_][\w]{0,59}")),
)


EVENT_LABELS = {
    "TOURNAMENT": ("대회 시작", "Tournament start", "大会開始"),
    "RESTOCK": ("입고 예정", "Scheduled restock", "入荷予定"),
}


def summarize(text, event=None):
    topic = next((label for expression, label in TOPICS if re.search(expression, text, re.I)), "새 게시물")
    lines = []
    if event:
        kind, start = event
        lines.append(EVENT_LABELS[kind][0] + " · " + start.strftime("%Y-%m-%d %H:%M KST"))
    for ko, _, _, pattern in FACTS:
        values = list(dict.fromkeys(pattern.findall(text)))[:6]
        if values:
            lines.append(ko + " · " + ", ".join(values))
    return topic, "\n".join(lines) or None


def translate_facts(summary, target):
    if not summary:
        return None
    labels = {ko: (en if target == "en" else ja) for ko, en, ja, _ in FACTS}
    labels.update({ko: en if target == "en" else ja for ko, en, ja in EVENT_LABELS.values()})
    translated = []
    for line in summary.splitlines():
        label, separator, value = line.partition(" · ")
        if label not in labels or not separator or not value:
            return None
        translated.append(labels[label] + separator + value)
    return "\n".join(translated)
