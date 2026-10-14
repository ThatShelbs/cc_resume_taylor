# Examples

Anonymized sample inputs in the layout the pipeline parses. Copy them into `workspace/input/`
(renamed to `in_profile*.docx`, `in_resume*.docx`, `in_job*.txt`) to try the command-line
pipeline without real data, or use them as a template for your own files.

| File | What it is |
|---|---|
| `make_examples.py` | Builds the sample files below (`python examples/make_examples.py`). Also imported by the tests. |
| `in_profile_example.docx`, `in_resume_example.docx`, `in_job_example.txt` | A fake profile, prior resume and job posting. |
| `fact_bank.example.yaml` | The shape of a fact bank, which a real run drafts with `resume-taylor-facts`. |
