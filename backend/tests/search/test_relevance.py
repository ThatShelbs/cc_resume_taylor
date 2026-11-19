from resume_taylor.search.prefs import Preferences
from resume_taylor.search.relevance import RoleFamily, function_words


def test_function_words_drop_level_and_filler():
    assert function_words("Senior Director, Medical Affairs") == ["medical", "affairs"]
    assert function_words("Head of Analytics") == ["analytics"]
    assert function_words("Director") == []


def test_gate_keeps_the_role_family_and_drops_the_rest():
    fam = RoleFamily(["Director, Medical Affairs", "Head of Analytics"])
    titles = [
        "Senior Director, Global Medical Affairs Strategy", "VP Analytics and Insights", "Director of Clinical Operations",
        "Account Executive", "Director, Sales",
    ]
    kept, off = fam.split([{"title": t} for t in titles])
    assert [p["title"] for p in kept] == titles[:2]
    assert off == 3


def test_gate_stays_open_without_function_words():
    fam = RoleFamily(["director"])
    assert not fam.active and fam.matches("Plant Manager")


def test_title_keywords_widen_the_family_and_feed_server_side_search():
    prefs = Preferences(titles=["Director, Data Science"], title_keywords=["machine learning", "data"])
    fam = RoleFamily.from_prefs(prefs)
    assert fam.matches("Principal Machine Learning Engineer") and fam.matches("Director of Data Platforms")
    assert "data science" in fam.search_terms()
