"""Is this posting for the role the person wants? A deterministic title gate applied right after a
company's postings are listed, so off-role postings are never hydrated, scored or listed one by one.

The role family comes from the wanted titles plus `title_keywords` (both editable in Preferences).
Level words (director, senior, head of) are ignored here because `filters.check_level` owns level;
what is compared is the function of the role: "Director, Medical Affairs" -> medical + affairs."""

import re

from .prefs import Preferences

_STOP = {
    "a", "an", "and", "the", "of", "for", "in", "at", "to", "with", "on", "or", "global", "us", "usa", "north", "america",
    "director", "directors", "senior", "sr", "snr", "junior", "jr", "associate", "assistant", "executive", "head", "chief",
    "vp", "svp", "evp", "avp", "vice", "president", "group", "principal", "lead", "manager", "managing", "officer",
    "i", "ii", "iii", "iv", "v",
}
MAX_TERMS = 6


def _stem(word: str) -> str:
    w = word.lower()
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 5 and w.endswith("ing"):
        return w[:-3]
    if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return w


def function_words(phrase: str) -> list[str]:
    """The words of a title that name the work, in order, with level words and filler removed."""
    words = re.findall(r"[a-z0-9+#]+", (phrase or "").lower())
    return [w for w in words if w not in _STOP]


class RoleFamily:
    def __init__(self, phrases: list[str]):
        self.terms: list[str] = []
        self._sets: list[frozenset[str]] = []
        for ph in phrases:
            fw = function_words(ph)
            if not fw:
                continue
            key = frozenset(_stem(w) for w in fw)
            if key not in self._sets:
                self._sets.append(key)
                self.terms.append(" ".join(fw))

    @classmethod
    def from_prefs(cls, prefs: Preferences, cand=None) -> "RoleFamily":
        titles = [*prefs.titles, *prefs.equivalent_titles, *prefs.title_keywords]
        if not titles and cand is not None:
            titles = list(cand.titles[:4])
        return cls(titles)

    @property
    def active(self) -> bool:
        """With no usable function words (for example only "director") the gate stays open."""
        return bool(self._sets)

    def matches(self, title: str) -> bool:
        if not self.active:
            return True
        have = {_stem(w) for w in function_words(title)}
        return any(s <= have for s in self._sets)

    def split(self, postings: list[dict]) -> tuple[list[dict], int]:
        kept = [p for p in postings if self.matches(p.get("title", ""))]
        return kept, len(postings) - len(kept)

    def search_terms(self) -> list[str]:
        """Short queries for APIs that search server-side (Workday, Eightfold, SmartRecruiters)."""
        return self.terms[:MAX_TERMS]
