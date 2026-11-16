"""`python -m resume_taylor.search.discover`: find the careers-page route for each target
company and save it to the shared route registry."""

import argparse
import json
from pathlib import Path

from resume_taylor.pipeline.runtime import stage

from .discovery import discover_routes
from .http import Client
from .routes import RouteBook


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Find careers-page routes for target companies.")
    ap.add_argument("--targets", required=True, help="JSON file: [{name, careers_url?}]")
    ap.add_argument("--routes", required=True)
    ap.add_argument("--cache-dir")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--out", help="write {name: route record} here")
    ap.add_argument("--model")
    ap.add_argument("--effort")
    args = ap.parse_args(argv)

    stage("discovering")
    targets = json.loads(Path(args.targets).read_text(encoding="utf-8"))
    companies = [{"name": t["name"], "careers_url": t.get("careers_url", "")} for t in targets if t.get("name")]
    client = Client(cache_dir=args.cache_dir)
    book = RouteBook(args.routes)
    print(f"Looking up careers pages for {len(companies)} companies...")
    results = discover_routes(client, book, companies, force=args.force, model=args.model, effort=args.effort)
    ok = sum(1 for r in results.values() if r.get("status") == "resolved")
    print(f"{ok} of {len(companies)} companies connected.")
    if args.out:
        Path(args.out).write_text(json.dumps(results, indent=2), encoding="utf-8")
    stage("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
