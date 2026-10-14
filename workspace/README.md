# workspace/

Data for the command-line workflow (`python -m resume_taylor.pipeline`). Everything inside
the three folders is git-ignored; only the `.gitkeep` files are tracked. The web app keeps
its data elsewhere (see Settings, "Your data").

- `input/`: `in_profile*`, `in_resume*`, `in_job*`, optional `fact_bank.yaml`
- `output/`: the newest `out_resume_...` files and their `_report.md`
- `archive/`: what `output/` held before the last run
