"""Writing-quality guards and the post-render ATS lint."""

import docx

from resume_taylor.pipeline.guards_quality import normalize_text, warn_ai_tells, warn_bullet_quality
from resume_taylor.pipeline.render.ats_lint import lint_docx
from resume_taylor.pipeline.render.docx_builder import build_docx
from resume_taylor.pipeline.runtime import WARNINGS


def _warnings_after(fn, *args):
    before = len(WARNINGS)
    fn(*args)
    return WARNINGS[before:]


def test_normalize_text_strips_invisible_and_curly_characters():
    assert normalize_text("It’s “done”​…") == 'It\'s "done"...'


def test_ai_tells_flag_buzzwords():
    out = _warnings_after(
        warn_ai_tells,
        "A results-driven leader.",
        {"Acme": ["Spearheaded a seamless migration.", "Cut churn 12%."]},
    )
    assert len(out) == 2
    assert "results-driven" in out[0] and "spearheaded" in out[1]


def test_ai_tells_ignore_plain_prose():
    assert not _warnings_after(warn_ai_tells, "Analytics lead.", {"Acme": ["Cut churn 12% with a new model."]})


def test_bullet_quality_flags_weak_repeated_and_long_openers():
    long_bullet = "Built " + "word " * 45
    out = _warnings_after(
        warn_bullet_quality,
        "One. Two.",
        {"Acme": ["Responsible for reports.", "Built a model.", long_bullet]},
    )
    text = "\n".join(out)
    assert "opens weakly" in text
    assert "'built'" in text
    assert "words; tighten" in text


def test_bullet_quality_flags_summary_length():
    out = _warnings_after(warn_bullet_quality, "Only one sentence.", {})
    assert any("summary has 1 sentence" in w for w in out)


def _data(dates="Jan 2020 - Present"):
    return {
        "first_name": "Ada",
        "last_name": "Lovelace",
        "email": "ada@example.com",
        "phone": "",
        "location": "",
        "summary": "Analyst.",
        "experience": [{"company": "Acme", "location": "", "dates": dates, "title": "Lead", "bullets": ["Did X."]}],
        "skills": ["Python"],
    }


def test_resume_uses_real_headings_and_clean_metadata(tmp_path):
    out = tmp_path / "r.docx"
    build_docx(_data(), out)
    d = docx.Document(str(out))
    assert {p.text for p in d.paragraphs if p.style.name == "Heading 1"} == {"Summary", "Experience", "Skills"}
    assert d.core_properties.author == "Ada Lovelace"
    assert d.core_properties.title == "Ada Lovelace - Resume"
    assert not _warnings_after(lint_docx, out, _data())


def test_lint_docx_flags_odd_dates(tmp_path):
    out = tmp_path / "r.docx"
    data = _data("Spring of last year")
    build_docx(data, out)
    assert any("standard" in w for w in _warnings_after(lint_docx, out, data))
