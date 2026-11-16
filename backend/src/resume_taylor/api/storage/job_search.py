"""The job search's files, under <data root>/job_search/. Everything is plain JSON written
atomically; postings keep their descriptions in separate text files so the index stays small."""

import csv
import io
import json
import re
from datetime import datetime
from pathlib import Path

from resume_taylor.search.normalize import norm_company
from resume_taylor.search.prefs import Preferences, load_prefs
from resume_taylor.search.routes import RouteBook

from .fs import atomic_write_text

MAX_TARGETS = 100
STAGES = ("prospect", "interested", "dismissed")
DISMISS_REASONS = ("not_interested", "wrong_level", "wrong_location", "pay", "company", "stale", "applied_elsewhere", "other")
KEEP_ON_MERGE = ("stage", "dismiss_reason", "notes", "project_id", "first_seen")
# fields the engine adds that the index does not need to keep
DROP_FROM_INDEX = ("description_text", "parsed_locations", "needs_detail", "apply_links")


class JobSearchError(ValueError):
    pass


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class JobSearchStore:
    def __init__(self, root: Path):
        self.root = Path(root)

    # -- paths -----------------------------------------------------------------------------------

    @property
    def prefs_path(self) -> Path:
        return self.root / "preferences.json"

    @property
    def targets_path(self) -> Path:
        return self.root / "targets.json"

    @property
    def routes_path(self) -> Path:
        return self.root / "company_routes.json"

    @property
    def postings_path(self) -> Path:
        return self.root / "postings.json"

    @property
    def cache_dir(self) -> Path:
        return self.root / "cache"

    def _read(self, path: Path, default):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return default

    def _write(self, path: Path, data) -> None:
        atomic_write_text(path, json.dumps(data, indent=2, default=str))

    # -- preferences -----------------------------------------------------------------------------

    def get_prefs(self) -> Preferences:
        return load_prefs(self.prefs_path)

    def save_prefs(self, prefs: Preferences) -> Preferences:
        prefs = prefs.normalized()
        self._write(self.prefs_path, prefs.model_dump())
        return prefs

    # -- targets ---------------------------------------------------------------------------------

    def targets(self) -> list[dict]:
        return self._read(self.targets_path, [])

    def routes(self) -> RouteBook:
        return RouteBook(self.routes_path)

    def targets_with_routes(self) -> list[dict]:
        book = self.routes()
        out = []
        for t in self.targets():
            r = book.get(t["name"]) or {}
            out.append({**t, "route": {
                "status": r.get("status", "unresolved"), "ats": r.get("ats", ""), "job_count": r.get("job_count"),
                "verified_at": r.get("verified_at"), "note": r.get("note", ""), "careers_url": r.get("careers_url", ""),
            }})
        return out

    def _save_targets(self, targets: list[dict]) -> None:
        if len(targets) > MAX_TARGETS:
            raise JobSearchError(f"A target list holds at most {MAX_TARGETS} companies.")
        self._write(self.targets_path, targets)

    def add_targets(self, items: list[dict], added_by: str = "user") -> dict:
        """Add companies (skipping duplicates). Returns {added, skipped, over_limit}."""
        targets = self.targets()
        have = {norm_company(t["name"]) for t in targets}
        added, skipped, over = [], [], []
        for it in items:
            name = re.sub(r"\s+", " ", str(it.get("name", ""))).strip()
            key = norm_company(name)
            if not key:
                continue
            if key in have:
                skipped.append(name)
                continue
            if len(targets) >= MAX_TARGETS:
                over.append(name)
                continue
            rec = {"id": key, "name": name, "careers_url": str(it.get("careers_url", "") or "").strip(),
                   "cluster": it.get("cluster", ""), "rationale": it.get("rationale", ""), "notes": "",
                   "added_by": added_by, "added_at": _now()}
            targets.append(rec)
            have.add(key)
            added.append(name)
        self._save_targets(targets)
        return {"added": added, "skipped": skipped, "over_limit": over, "total": len(targets)}

    def replace_targets(self, items: list[dict]) -> None:
        self._write(self.targets_path, [])
        self.add_targets(items)

    def update_target(self, tid: str, patch: dict) -> dict:
        targets = self.targets()
        for t in targets:
            if t["id"] == tid:
                for k in ("name", "careers_url", "notes"):
                    if k in patch and patch[k] is not None:
                        t[k] = str(patch[k]).strip()
                if "careers_url" in patch:
                    self.routes().forget(t["name"])  # a new URL means the old route can't be trusted
                    book = self.routes()
                    book.forget(t["name"])
                    book.save()
                self._save_targets(targets)
                return t
        raise JobSearchError("No such company in your list.")

    def remove_target(self, tid: str) -> None:
        self._save_targets([t for t in self.targets() if t["id"] != tid])

    @staticmethod
    def parse_import(text: str) -> list[dict]:
        """Lines of 'Name' or 'Name, careers URL' (also a CSV with a header row)."""
        items = []
        rows = list(csv.reader(io.StringIO(text.strip())))
        if rows and [c.strip().lower() for c in rows[0][:2]] in (["name", "careers_url"], ["company", "careers_url"], ["company", "url"], ["name", "url"], ["company"], ["name"]):
            rows = rows[1:]
        for row in rows:
            row = [c.strip() for c in row if c is not None]
            if not row or not row[0]:
                continue
            name, url = row[0], ""
            for cell in row[1:]:
                if cell.lower().startswith(("http://", "https://", "www.")) or "." in cell and " " not in cell:
                    url = cell if cell.lower().startswith("http") else "https://" + cell
                    break
            if name.lower().startswith(("http://", "https://")):
                continue
            items.append({"name": name, "careers_url": url})
        return items

    # -- suggestions -----------------------------------------------------------------------------

    def save_suggestions(self, data: dict) -> None:
        self._write(self.root / "suggestions" / "latest.json", {**data, "created_at": _now()})

    def latest_suggestions(self) -> dict | None:
        return self._read(self.root / "suggestions" / "latest.json", None)

    # -- postings --------------------------------------------------------------------------------

    def _postings(self) -> dict:
        return self._read(self.postings_path, {})

    def _description_path(self, pid: str) -> Path:
        if not re.fullmatch(r"[a-f0-9]{6,40}", pid):
            raise JobSearchError("Not a posting id.")
        return self.root / "postings" / f"{pid}.txt"

    def description(self, pid: str) -> str:
        try:
            return self._description_path(pid).read_text(encoding="utf-8")
        except OSError:
            return ""

    def merge_run(self, report: dict, run_id: str) -> dict:
        """Fold a finished run into the posting index. User choices (stage, notes, project) survive."""
        index = self._postings()
        for p in [*report.get("results", []), *report.get("more", [])]:
            prior = index.get(p["id"], {})
            rec = {k: v for k, v in p.items() if k not in DROP_FROM_INDEX}
            for k in KEEP_ON_MERGE:
                if k in prior:
                    rec[k] = prior[k]
            rec.setdefault("stage", "prospect")
            rec["last_seen"] = _now()
            rec["is_new"] = p["id"] not in index
            rec["run_ids"] = [*prior.get("run_ids", []), run_id][-20:]
            rec["in_top"] = p in report.get("results", []) or prior.get("in_top", False)
            index[p["id"]] = rec
            if p.get("description_text"):
                atomic_write_text(self._description_path(p["id"]), p["description_text"])
        # a posting that was new last run is no longer "new" once a later run has seen it
        seen_now = {p["id"] for p in [*report.get("results", []), *report.get("more", [])]}
        for pid, rec in index.items():
            if pid not in seen_now:
                rec["is_new"] = False
        self._write(self.postings_path, index)
        slim = {**report}
        for key in ("results", "more"):
            slim[key] = [{k: v for k, v in p.items() if k not in DROP_FROM_INDEX} for p in report.get(key, [])]
        self._write(self.root / "runs" / f"{run_id}.json", slim)
        return {"results": len(report.get("results", [])), "total_postings": len(index)}

    def add_posting(self, posting: dict) -> dict:
        """A posting the user imported by URL."""
        index = self._postings()
        prior = index.get(posting["id"], {})
        rec = {k: v for k, v in posting.items() if k not in DROP_FROM_INDEX}
        rec.update({"stage": prior.get("stage", "interested"), "first_seen": prior.get("first_seen", _now()), "last_seen": _now(),
                    "is_new": False, "imported": True, "project_id": prior.get("project_id", ""), "dismiss_reason": "", "notes": prior.get("notes", "")})
        index[posting["id"]] = rec
        if posting.get("description_text"):
            atomic_write_text(self._description_path(posting["id"]), posting["description_text"])
        self._write(self.postings_path, index)
        return rec

    def list_postings(self, *, stage: str | None = None, only_new: bool = False, freshness: str | None = None,
                      min_score: int = 0) -> list[dict]:
        out = []
        for rec in self._postings().values():
            if stage and rec.get("stage") != stage:
                continue
            if only_new and not rec.get("is_new"):
                continue
            if freshness and rec.get("freshness") != freshness:
                continue
            if (rec.get("fit") or {}).get("total", 0) < min_score:
                continue
            out.append(rec)
        out.sort(key=lambda r: ((r.get("fit") or {}).get("total", 0), r.get("last_seen", "")), reverse=True)
        return out

    def get_posting(self, pid: str) -> dict:
        rec = self._postings().get(pid)
        if not rec:
            raise JobSearchError("No such posting.")
        return rec

    def posting_with_text(self, pid: str) -> dict:
        return {**self.get_posting(pid), "description_text": self.description(pid)}

    def patch_posting(self, pid: str, patch: dict) -> dict:
        index = self._postings()
        rec = index.get(pid)
        if not rec:
            raise JobSearchError("No such posting.")
        if patch.get("stage") is not None:
            if patch["stage"] not in STAGES:
                raise JobSearchError(f"Stage must be one of {', '.join(STAGES)}.")
            rec["stage"] = patch["stage"]
            rec["dismiss_reason"] = patch.get("dismiss_reason") or ("" if patch["stage"] != "dismissed" else rec.get("dismiss_reason", ""))
        if patch.get("dismiss_reason") is not None and patch["dismiss_reason"] in DISMISS_REASONS:
            rec["dismiss_reason"] = patch["dismiss_reason"]
        if patch.get("notes") is not None:
            rec["notes"] = str(patch["notes"])
        rec["is_new"] = False
        self._write(self.postings_path, index)
        return rec

    def update_posting(self, pid: str, fields: dict) -> dict:
        """Internal: set arbitrary fields (project link, verification)."""
        index = self._postings()
        if pid not in index:
            raise JobSearchError("No such posting.")
        index[pid].update(fields)
        self._write(self.postings_path, index)
        return index[pid]

    def count_new_strong(self, threshold: int = 80) -> int:
        return sum(1 for r in self._postings().values()
                   if r.get("is_new") and r.get("stage") == "prospect" and (r.get("fit") or {}).get("total", 0) >= threshold)

    # -- runs ------------------------------------------------------------------------------------

    def list_runs(self) -> list[dict]:
        runs = []
        for f in sorted((self.root / "runs").glob("*.json"), reverse=True)[:30] if (self.root / "runs").exists() else []:
            r = self._read(f, {})
            runs.append({"id": f.stem, "started": r.get("started"), "finished": r.get("finished"), "count": r.get("count"),
                         "depth": r.get("depth"), "found": len(r.get("results", [])), "rejected": len(r.get("rejected", [])),
                         "tier": r.get("tier"), "total_seconds": (r.get("timings") or {}).get("total")})
        return runs

    def get_run(self, run_id: str) -> dict:
        if not re.fullmatch(r"[A-Za-z0-9_-]{6,40}", run_id):
            raise JobSearchError("Not a run id.")
        data = self._read(self.root / "runs" / f"{run_id}.json", None)
        if data is None:
            raise JobSearchError("No such run.")
        return data
