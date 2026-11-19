"""One posting schema for every source, plus the parsers that fill it (pay, level,
"posted N days ago", work mode). Everything here is deterministic."""

import hashlib
import html as htmllib
import re
from datetime import datetime, timedelta, timezone

from .prefs import LEVELS


def new_posting(**kw) -> dict:
    """A posting dict with every field present."""
    base = {
        "id": "", "source": "", "ats": "", "company": "", "title": "", "req_id": "",
        "locations": [], "work_mode": "unknown", "posted_at": None, "posted_at_source": "",
        "closes_at": None, "pay_min": None, "pay_max": None, "currency": "", "pay_period": "",
        "pay_text": "", "url": "", "apply_url": "", "also_listed_on": [], "description_text": "",
        "level": "", "read_by_claude": False, "aggregator_only": False, "external_id": "",
    }
    base.update(kw)
    if not base["id"]:
        base["id"] = make_id(base)
    if not base["level"]:
        base["level"] = title_level(base["title"])
    if base["work_mode"] == "unknown":
        base["work_mode"] = detect_work_mode(" ".join(base["locations"]), base["description_text"])
    return base


def make_id(p: dict) -> str:
    key = "|".join([
        norm_company(p.get("company", "")), p.get("ats", ""), p.get("external_id") or p.get("req_id") or p.get("url", ""),
        "" if (p.get("external_id") or p.get("req_id") or p.get("url")) else norm_title(p.get("title", "")),
    ])
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


_LEGAL = {"inc", "llc", "ltd", "corp", "corporation", "co", "company", "plc", "gmbh", "group", "holdings", "the"}
# Trailing words that name a descriptor or a division, not a different company: "Veeva Systems" is
# Veeva, "Johnson & Johnson MedTech" is Johnson & Johnson. Stripped only while a real name remains.
_DESCRIPTORS = [
    ["innovative", "medicine"], ["consumer", "health"], ["systems"], ["technologies"], ["technology"], ["labs"],
    ["software"], ["pharmaceuticals"], ["pharmaceutical"], ["pharma"], ["therapeutics"], ["biosciences"],
    ["medicine"], ["medtech"], ["healthcare"], ["health"], ["biotech"], ["international"], ["global"],
    ["america"], ["americas"], ["usa"], ["us"],
]
# Abbreviations and sibling names that point at one company (normalized, letters and digits only).
COMPANY_ALIASES = {
    "jj": "johnsonjohnson", "jnj": "johnsonjohnson", "janssen": "johnsonjohnson",
    "gsk": "glaxosmithkline", "bms": "bristolmyerssquibb", "bristolmyers": "bristolmyerssquibb",
    "msd": "merck", "mercksharpdohme": "merck", "az": "astrazeneca", "pg": "procterandgamble",
    "ge": "generalelectric", "ibm": "internationalbusinessmachines", "lilly": "elililly",
    "boehringer": "boehringeringelheim", "jpmorgan": "jpmorganchase", "jpmc": "jpmorganchase",
}
_DESC_MAX_PASSES = 3


def _words(name: str) -> list[str]:
    s = name.lower().replace("&amp;", "&")
    s = re.sub(r"(?<=\b[a-z])&(?=[a-z]\b)", "", s)  # J&J -> jj
    s = s.replace("&", " ")
    return re.findall(r"[a-z0-9]+", s)


def company_key(name: str) -> str:
    """One stable key per company, tolerant of legal suffixes, descriptors, divisions and common
    abbreviations. Equal keys mean the same company; never used to display a name."""
    words = [w for w in _words(name) if w not in _LEGAL]
    while words and words[-1] == "and":  # "Eli Lilly and Company"
        words.pop()
    if not words:
        return ""
    for _ in range(_DESC_MAX_PASSES):
        for tail in _DESCRIPTORS:
            n = len(tail)
            if len(words) > n and words[-n:] == tail:
                rest = "".join(words[:-n])
                if len(rest) >= 4 or rest in COMPANY_ALIASES:
                    words = words[:-n]
                    break
        else:
            break
    key = "".join(words)
    return COMPANY_ALIASES.get(key, key)


def norm_company(name: str) -> str:
    return company_key(name)


def same_company(a: str, b: str) -> bool:
    """True when two names plausibly mean one company: equal keys, or one is the initials of the other."""
    ka, kb = company_key(a), company_key(b)
    if not ka or not kb:
        return False
    if ka == kb:
        return True
    for short, long_name in ((ka, b), (kb, a)):
        initials = "".join(w[0] for w in _words(long_name) if w not in _LEGAL)
        if 2 <= len(short) <= 4 and short == initials:
            return True
    return False


def norm_title(title: str) -> str:
    t = title.lower()
    t = re.sub(r"\b(sr|snr)\.?\b", "senior", t)
    t = re.sub(r"\(.*?\)", " ", t)
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


# -- text ---------------------------------------------------------------------------------

def html_to_text(raw: str) -> str:
    if not raw:
        return ""
    s = htmllib.unescape(htmllib.unescape(raw))  # ATS APIs often double-escape their HTML
    s = re.sub(r"(?is)<(script|style).*?</\1>", " ", s)
    s = re.sub(r"(?i)<br\s*/?>|</(p|div|li|h[1-6]|ul|ol|tr)>", "\n", s)
    s = re.sub(r"(?i)<li[^>]*>", "- ", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = s.replace("\xa0", " ")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n\n", s)
    return s.strip()


# -- pay ----------------------------------------------------------------------------------

_AMOUNT = r"(?P<cur>[$£€])\s?(?P<num>\d[\d.,]*)\s?(?P<k>[kK])?"
_RANGE_RE = re.compile(
    rf"{_AMOUNT}\s*(?:-|–|—|to|and)\s*(?:[$£€]\s?)?(?P<num2>\d[\d.,]*)\s?(?P<k2>[kK])?", re.I
)
_CUR = {"$": "USD", "£": "GBP", "€": "EUR"}


def parse_number(s: str) -> float | None:
    """'186,000' / '186.014,40' / '194.600.00' / '1.500' to a float."""
    s = s.strip().rstrip(".,")
    if not re.search(r"\d", s):
        return None
    seps = [i for i, ch in enumerate(s) if ch in ".,"]
    if not seps:
        return float(s)
    last = seps[-1]
    tail = s[last + 1:]
    mixed = len({s[i] for i in seps}) > 1
    decimal_last = mixed or len(tail) != 3 or len(seps) > 1 and s[seps[-1]] != s[seps[-2]]
    if len(seps) > 1 and not mixed and len(tail) == 3:
        decimal_last = False  # 1.234.567
    if decimal_last:
        whole = re.sub(r"[.,]", "", s[:last])
        return float(f"{whole}.{tail}")
    return float(re.sub(r"[.,]", "", s))


def _amount(num: str, k: str | None) -> float | None:
    v = parse_number(num)
    if v is None:
        return None
    return v * 1000 if k else v


def parse_pay(text: str) -> dict:
    """Find the first pay range (or single amount) in free text. Returns
    {pay_min, pay_max, currency, pay_period}; fields are None/'' when nothing credible is found."""
    out = {"pay_min": None, "pay_max": None, "currency": "", "pay_period": ""}
    if not text:
        return out
    hourly = bool(re.search(r"per hour|/\s?hr|/\s?hour|hourly", text, re.I))
    for m in _RANGE_RE.finditer(text):
        lo = _amount(m.group("num"), m.group("k"))
        hi = _amount(m.group("num2"), m.group("k2") or m.group("k"))
        if lo is None or hi is None:
            continue
        if lo > hi:
            lo, hi = hi, lo
        return _finish_pay(out, lo, hi, m.group("cur"), hourly)
    for m in re.finditer(_AMOUNT, text):
        v = _amount(m.group("num"), m.group("k"))
        if v is not None and (v >= 20000 or hourly or m.group("k")):
            return _finish_pay(out, v, v, m.group("cur"), hourly)
    return out


def _finish_pay(out: dict, lo: float, hi: float, cur: str, hourly: bool) -> dict:
    if hourly or hi < 1000:
        if hi >= 1000:
            return out
        lo, hi, period = lo * 2080, hi * 2080, "hour"
    else:
        period = "year"
        if hi < 20000:  # a stray small number, not a salary
            return out
    out.update(pay_min=round(lo), pay_max=round(hi), currency=_CUR.get(cur, ""), pay_period=period)
    return out


def with_pay(posting: dict, text: str) -> dict:
    """Fill the posting's pay fields from text, unless a source already supplied them."""
    if posting.get("pay_max"):
        return posting
    found = parse_pay(text)
    if found["pay_max"]:
        posting.update(found)
        m = _RANGE_RE.search(text) or re.search(_AMOUNT, text)
        posting["pay_text"] = text[max(0, m.start() - 20): m.end() + 40].strip().replace("\n", " ") if m else ""
    return posting


# -- level --------------------------------------------------------------------------------

_LEVEL_PATTERNS = [
    ("executive", r"\b(chief [a-z ]*officer|c[a-z]o|(?<!vice )president|general manager|managing director)\b"),
    ("vp", r"\b(vice president|vp|svp|evp|avp)\b"),
    ("senior_director", r"\b(senior director|sr\.? director|executive director|associate vice|group director)\b"),
    ("director", r"\b(director|head of|head,)\b"),
    ("senior_manager", r"\b(senior manager|sr\.? manager)\b"),
    ("manager", r"\b(manager|lead)\b"),
]


def level_rank(level: str) -> int:
    return LEVELS.index(level) if level in LEVELS else 0


def title_level(title: str, equivalents: list[str] | tuple = ()) -> str:
    t = (title or "").lower()
    found = "ic"
    for level, pat in _LEVEL_PATTERNS:
        if re.search(pat, t):
            found = level
            break
    if level_rank(found) < level_rank("director"):
        if any(e.strip() and e.strip().lower() in t for e in equivalents):
            return "director"
    return found


# -- dates --------------------------------------------------------------------------------

def parse_iso(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, (int, float)):
        ts = value / 1000 if value > 1e11 else value
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        try:
            dt = datetime.strptime(str(value)[:10], "%Y-%m-%d")
        except ValueError:
            return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def parse_posted_ago(text: str) -> int | None:
    """'Posted 3 Days Ago', 'Posted Today', '2 weeks ago', '30+ days ago' to whole days."""
    t = (text or "").lower()
    if re.search(r"\btoday\b|just posted|just now|\b\d+\s*(minute|hour)s?\b", t):
        return 0
    if "yesterday" in t:
        return 1
    m = re.search(r"(\d+)\+?\s*(day|week|month)s?", t)
    if not m:
        return None
    n = int(m.group(1))
    return n * {"day": 1, "week": 7, "month": 30}[m.group(2)]


def days_ago_to_iso(days: int, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return (now - timedelta(days=days)).isoformat(timespec="seconds")


# -- work mode ----------------------------------------------------------------------------

def detect_work_mode(location_text: str, description: str = "") -> str:
    loc = (location_text or "").lower()
    desc = (description or "").lower()
    if "hybrid" in loc:
        return "hybrid"
    if "remote" in loc:
        return "remote"
    if re.search(r"\bhybrid\b|\d\s*days? (per|a|each) week (in|on)", desc[:3000]):
        return "hybrid"
    if re.search(r"fully remote|remote[- ]first|this is a remote|100% remote|remote position|work from home", desc[:3000]):
        return "remote"
    if re.search(r"on[- ]?site|in[- ]office|in[- ]person", desc[:3000]):
        return "onsite"
    return "unknown"
