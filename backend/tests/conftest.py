"""Fixtures shared by the pipeline and app tests."""

import shutil

import pytest

from resume_taylor.api.storage.paths import Paths
from resume_taylor.sample_data import demo_data
from resume_taylor.search import render
from support import DENY_FIXTURE, write_docx


@pytest.fixture(autouse=True)
def no_headless_browser(monkeypatch):
    """Tests never open a real browser; a test that needs a rendered page swaps in a fake `render`."""
    monkeypatch.setattr(render, "ENABLED", False)


@pytest.fixture
def workspace(tmp_path):
    """A data root with the demo persona's inputs."""
    paths = Paths(tmp_path)
    paths.ensure()
    write_docx(demo_data.PROFILE, paths.input_dir / "in_profile.docx")
    write_docx(demo_data.RESUME, paths.input_dir / "in_resume_Jordan-Rivera.docx")
    paths.fact_bank_path.write_text(demo_data.FACT_BANK, encoding="utf-8")
    shutil.copy(DENY_FIXTURE, paths.deny_path)
    return paths
