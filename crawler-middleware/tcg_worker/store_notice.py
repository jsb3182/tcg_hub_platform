"""Recognize one explicitly scheduled tournament or delivery from a Korean shop's timeline."""
import re
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))
SCHEDULE = re.compile(
    r"^\s*(?:[·•-]\s*)?(?P<kind>대회|대회 시작|입고)\s*(?:일시|예정 일시)\s*[:：]\s*"
    r"(?P<y>20\d{2})(?:[./-]|년\s*)(?P<m>\d{1,2})(?:[./-]|월\s*)(?P<d>\d{1,2})일?"
    r"(?:\s*\([월화수목금토일](?:요일)?\))?\s+"
    r"(?:(?P<period>오전|오후)\s*)?(?P<h>\d{1,2})(?::(?P<minute>\d{2})|시(?:\s*(?P<kminute>\d{1,2})분)?)"
    r"(?:\s*\(?(?:KST|한국\s*시간)\)?)?\s*$", re.M | re.I)


def scheduled_event(text):
    if re.search(r"취소|연기|미정|루머|유출|미\s*확[인정]|잠정|변경\s*전|"
                 r"cancel|postpon|unconfirmed|tentative|rumou?r|leak|未定|中止|未確認|未確定", text, re.I):
        return None
    matches = list(SCHEDULE.finditer(text))
    if len(matches) != 1:
        return None
    event = matches[0]
    hour = int(event["h"])
    if event["period"]:
        if not 1 <= hour <= 12:
            return None
        hour = hour % 12 + (12 if event["period"] == "오후" else 0)
    try:
        start = datetime(int(event["y"]), int(event["m"]), int(event["d"]), hour,
                         int(event["minute"] or event["kminute"] or 0), tzinfo=KST)
    except ValueError:
        return None
    return ("RESTOCK" if event["kind"] == "입고" else "TOURNAMENT"), start
