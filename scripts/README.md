# Scripts

Run from the repo root (`python scripts/<name>.py`). None of them are imported by the app.

| Script | What it does | Who runs it |
|---|---|---|
| `check_no_personal_data.py` | Fails if a resume, `.env`, API key or project folder is (about to be) committed. `--install-hook` makes it a pre-commit hook. | CI, contributors |
| `doctor.py` | Plain-English health check (Python, Claude, Word, ports). | `windows/Doctor.bat` |
| `export_openapi.py` | Writes the server's OpenAPI schema for `npm run gen:api`. | `frontend` npm script |
| `make_demo_workspace.py` | Builds a demo data folder around the fictional applicant. | `capture_screenshots.py`, contributors |
| `capture_screenshots.py` | Retakes the README screenshots against a demo workspace (needs Playwright). | contributors |
| `make_template_previews.py` | Re-renders the template thumbnails in `frontend/public/templates/` (needs Word). | contributors |
| `make_brand_assets.py` | Renders the icon, banner and social preview from `frontend/public/favicon.svg` (needs Playwright). | contributors |
| `windows/Doctor.bat`, `windows/Update.bat`, `windows/Create Desktop Shortcut.bat` (+ `create_desktop_shortcut.ps1`) | Double-click helpers for non-technical Windows users. | end users |
