"""`python -m resume_taylor.search.suggest`: ideate target companies and write them to --out.

Used by the app's "Suggest companies for me". Works at every setup tier."""

import argparse
import json
from pathlib import Path

from resume_taylor.pipeline.runtime import stage

from .candidate import build_candidate
from .ideation import CLUSTERS, ideate
from .prefs import load_prefs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Suggest target companies.")
    ap.add_argument("--prefs")
    ap.add_argument("--profile")
    ap.add_argument("--resume")
    ap.add_argument("--fact-bank")
    ap.add_argument("--exclude", help="JSON file: list of company names to skip")
    ap.add_argument("--count", type=int, default=30)
    ap.add_argument("--clusters", default=",".join(CLUSTERS))
    ap.add_argument("--out", required=True)
    ap.add_argument("--model")
    ap.add_argument("--effort")
    args = ap.parse_args(argv)

    stage("preparing")
    prefs = load_prefs(args.prefs)
    cand = build_candidate(*(Path(p) if p else None for p in (args.profile, args.resume, args.fact_bank)), prefs)
    exclude = json.loads(Path(args.exclude).read_text(encoding="utf-8")) if args.exclude else []
    stage("ideating")
    print(f"Thinking about companies for you ({cand.tier} setup)...")
    companies = ideate(cand, max(1, min(100, args.count)), clusters=args.clusters.split(","), exclude=exclude,
                       model=args.model, effort=args.effort)
    print(f"{len(companies)} companies suggested.")
    Path(args.out).write_text(json.dumps({"tier": cand.tier, "companies": companies}, indent=2), encoding="utf-8")
    stage("done")
    return 0 if companies else 1


if __name__ == "__main__":
    raise SystemExit(main())
