"""Build backend/src/resume_taylor/resources/us_places.csv.gz from the US Census Gazetteer.

The job search's distance rule works with a small built-in list of major cities and suburbs.
This optional script extends it to every US place, so a radius check can place small towns.
It downloads one public-domain file (about 1.5 MB) from census.gov, so it is a developer
step you run on purpose, not something the app does:

    python scripts/build_places.py

The output holds name, state, latitude and longitude, one place per row.
"""

import csv
import gzip
import io
import re
import urllib.request
import zipfile
from pathlib import Path

URL = "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2023_Gazetteer/2023_Gaz_place_national.zip"
OUT = Path(__file__).resolve().parents[1] / "backend" / "src" / "resume_taylor" / "resources" / "us_places.csv.gz"
SUFFIX = re.compile(r"\s+(city|town|village|borough|municipality|CDP|city and borough|urban county)$", re.I)


def main() -> None:
    print(f"Downloading {URL} ...")
    raw = urllib.request.urlopen(URL, timeout=60).read()
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        name = next(n for n in z.namelist() if n.endswith(".txt"))
        text = z.read(name).decode("latin-1")
    rows = csv.DictReader(io.StringIO(text), delimiter="\t")
    seen: set[tuple[str, str]] = set()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(OUT, "wt", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        for r in rows:
            r = {k.strip(): (v or "").strip() for k, v in r.items()}
            place = SUFFIX.sub("", r["NAME"])
            key = (place.lower(), r["USPS"])
            if key in seen:
                continue
            seen.add(key)
            writer.writerow([place, r["USPS"], r["INTPTLAT"], r["INTPTLONG"]])
    print(f"Wrote {len(seen)} places to {OUT}")


if __name__ == "__main__":
    main()
