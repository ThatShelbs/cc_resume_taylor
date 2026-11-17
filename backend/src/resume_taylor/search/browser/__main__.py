"""`python -m resume_taylor.search.browser login <site> --dir <job_search dir>`: opens a Chrome window
at the site's sign-in page and waits while you sign in yourself (2FA and CAPTCHAs included)."""

import argparse
from pathlib import Path

from resume_taylor.pipeline.runtime import stage

from . import sites
from .session import BrowserSession, BrowserUnavailable
from .state import LABELS, SITES, AccountState, profile_dir


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Sign in to a job site in a real browser window.")
    ap.add_argument("action", choices=["login"])
    ap.add_argument("site", choices=SITES)
    ap.add_argument("--dir", required=True, help="the job_search data folder")
    ap.add_argument("--timeout", type=int, default=600)
    args = ap.parse_args(argv)
    state = AccountState(Path(args.dir) / "accounts.json")
    stage("waiting for sign-in")
    print(f"A Chrome window is opening. Sign in to {LABELS[args.site]} yourself, then leave the window; it closes on its own.")
    try:
        with BrowserSession(profile_dir(args.dir, args.site)) as s:
            s.goto(sites.LOGIN[args.site])
            ok = s.wait_until_signed_in(args.site, sites.SIGNED_IN_URL[args.site], args.timeout)
    except BrowserUnavailable as exc:
        print(str(exc))
        return 1
    if not ok:
        print("Sign-in was not completed.")
        return 1
    state.mark_connected(args.site)
    stage("done")
    print(f"{LABELS[args.site]} is connected. Only the browser session is kept on this computer.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
