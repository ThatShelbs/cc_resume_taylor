"""The pre-generation interview: question job, saving answers, and what flows into later runs."""

import json
import textwrap
import time

from resume_taylor.api.services import pipeline_runner
from resume_taylor.api.storage import facts as facts_mod
from resume_taylor.api.storage.paths import Paths
from support import JOB_TEXT

FAKE_INTERVIEW = textwrap.dedent("""\
    import json, sys
    from pathlib import Path
    args = sys.argv[1:]
    out = Path(args[args.index("--out") + 1])
    print("::stage preparing", flush=True)
    out.write_text(json.dumps({
        "seniority": "director", "target_title": "Director",
        "questions": [{"id": "q1", "question": "Tell me about influencing a VP.", "why": "Senior role."}],
        "skills": [{"name": "Databricks", "kind": "hard", "status": "gap"}],
    }))
    print("::stage done", flush=True)
    """)


def _wait(client, job_id):
    end = time.time() + 20
    while client.get(f"/api/jobs/{job_id}").json()["status"] not in ("succeeded", "failed") and time.time() < end:
        time.sleep(0.05)
    return client.get(f"/api/jobs/{job_id}").json()


def _project(client):
    return client.post("/api/projects", json={"job_text": JOB_TEXT, "role": "Director"}).json()["project"]["id"]


def test_questions_job_caches_result(client, tmp_path, monkeypatch):
    fake = tmp_path / "fake_interview.py"
    fake.write_text(FAKE_INTERVIEW, encoding="utf-8")
    monkeypatch.setattr(Paths, "interview_command", property(lambda self: [str(fake)]))
    pid = _project(client)
    assert client.get(f"/api/projects/{pid}/interview").json() == {"exists": False}

    job = client.post(f"/api/projects/{pid}/interview/questions").json()
    done = _wait(client, job["id"])
    assert done["status"] == "succeeded" and done["result"]["questions"][0]["id"] == "q1"
    cached = client.get(f"/api/projects/{pid}/interview").json()
    assert cached["exists"] and cached["skills"][0]["name"] == "Databricks"


def test_answers_become_facts_profile_skills_and_notes(client, workspace):
    pid = _project(client)
    before = len(facts_mod.read_facts(workspace.fact_bank_path))
    body = {
        "answers": [
            {"question": "Influencing a VP?", "text": "I got the VP of Product to fund a pricing test after presenting results.", "employer": "general"},
            {"question": "Skipped", "text": "   "},
        ],
        "skills": [
            {"name": "Databricks", "kind": "hard", "status": "no"},
            {"name": "Airflow", "kind": "hard", "status": "have"},
            {"name": "Executive influence", "kind": "soft", "status": "have", "note": "Presented quarterly results to the VP of Product."},
        ],
    }
    saved = client.post(f"/api/projects/{pid}/interview/answers", json=body).json()
    assert saved["facts_added"] == 2 and "Airflow" in saved["skills_added"]

    facts = facts_mod.read_facts(workspace.fact_bank_path)
    assert len(facts) == before + 2
    assert facts[-1].id > facts[before - 1].id and "interview" in facts[-1].tags
    profile = client.get("/api/profile").json()["profile"]
    titles = {s["title"]: s["items"] for s in profile["sections"]}
    assert "Airflow" in titles["Software/Tools"] and "Executive influence" in titles["Skills"]
    assert "Databricks" not in json.dumps(profile)  # a denied skill is never persisted

    notes = (workspace.projects_dir / pid / "interview_notes.txt").read_text(encoding="utf-8")
    assert "VP of Product" in notes and "Databricks" not in notes
    # A second save with the same text does not duplicate facts.
    again = client.post(f"/api/projects/{pid}/interview/answers", json=body).json()
    assert again["facts_added"] == 0


def test_pipeline_command_passes_interview_notes(workspace, tmp_path):
    notes = tmp_path / "notes.txt"
    common = dict(job_text=tmp_path / "j.txt", out_dir=tmp_path, result_json=tmp_path / "r.json", template="classic")
    assert "--extra-context" not in pipeline_runner.pipeline_command(workspace, **common, extra_context=notes)
    notes.write_text("Q: x\nA: y", encoding="utf-8")
    assert "--extra-context" in pipeline_runner.pipeline_command(workspace, **common, extra_context=notes)
    rendered = pipeline_runner.pipeline_command(workspace, **common, extra_context=notes, render_json=tmp_path / "r.json")
    assert "--extra-context" not in rendered
