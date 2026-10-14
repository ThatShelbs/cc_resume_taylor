# Resume Taylor backend

Python package `resume_taylor` (src layout, `src/resume_taylor/`). Two halves that share a few small modules:

| Folder / module | What it is |
|---|---|
| `pipeline/` | The tailoring engine and its command line (`python -m resume_taylor.pipeline`). Deterministic parsing, the two Claude calls, the validation guards, `.docx`/`.pdf` output. Knows nothing about the web. |
| `api/` | The FastAPI backend of the web app. `main.py` wires it together; `routers/` is the HTTP API (one module per area), `services/` is what routes call (background jobs, the pipeline runner, live checks, sample data), `storage/` reads and writes files on disk. It runs the pipeline as a subprocess for every generation. |
| `layout.py` | Where the repo's folders are (stdlib only, so the launcher can use it before packages are installed). |
| `config.py` | Settings from the environment and `.env`, plus the command-line workflow's default folders (`workspace/`). |
| `claude_cli.py` | Running the `claude` CLI as a text-generation step; used by both halves. |
| `launcher.py` | Starts the server and opens the browser (`python -m resume_taylor`). |
| `sample_data/` | The fictional demo applicant. |
| `resources/` | The starter never-claim list. |

Dependencies flow one way: `api` imports `pipeline`, never the reverse.

Console scripts (after `pip install -e backend`): `resume-taylor` (the app), `resume-taylor-generate` (the pipeline),
`resume-taylor-facts` (draft a fact bank).

## Develop

```bash
pip install -e "backend[dev]"
cd backend && python -m pytest -q      # no test makes a Claude call
ruff check backend                     # from the repo root
```

`tests/pipeline/` mirrors the pipeline modules; `tests/api/` covers the HTTP API, stores and job runner.
`tests/support.py` builds the temporary workspaces both use.
