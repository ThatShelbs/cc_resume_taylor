"""Straight-line distance for the location rule. Place names resolve through a bundled list
of major US cities and suburbs; `resources/us_places.csv.gz` (built by
`scripts/build_places.py` from the Census Gazetteer) extends it when present. No drive time,
and no network calls."""

import csv
import gzip
import math
import re
from functools import lru_cache

from resume_taylor.layout import PACKAGE_DIR

STATES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR", "california": "CA", "colorado": "CO",
    "connecticut": "CT", "delaware": "DE", "district of columbia": "DC", "florida": "FL", "georgia": "GA",
    "hawaii": "HI", "idaho": "ID", "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD", "massachusetts": "MA",
    "michigan": "MI", "minnesota": "MN", "mississippi": "MS", "missouri": "MO", "montana": "MT",
    "nebraska": "NE", "nevada": "NV", "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM",
    "new york": "NY", "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC", "south dakota": "SD",
    "tennessee": "TN", "texas": "TX", "utah": "UT", "vermont": "VT", "virginia": "VA", "washington": "WA",
    "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
}
STATE_CODES = set(STATES.values())

# City|ST|lat|lon (approximate city-center coordinates).
_BUILTIN = """
New York|NY|40.71|-74.01;Los Angeles|CA|34.05|-118.24;Chicago|IL|41.88|-87.63;Houston|TX|29.76|-95.37
Phoenix|AZ|33.45|-112.07;Philadelphia|PA|39.95|-75.17;San Antonio|TX|29.42|-98.49;San Diego|CA|32.72|-117.16
Dallas|TX|32.78|-96.80;San Jose|CA|37.34|-121.89;Austin|TX|30.27|-97.74;Jacksonville|FL|30.33|-81.66
San Francisco|CA|37.77|-122.42;Columbus|OH|39.96|-83.00;Charlotte|NC|35.23|-80.84;Indianapolis|IN|39.77|-86.16
Seattle|WA|47.61|-122.33;Denver|CO|39.74|-104.99;Washington|DC|38.91|-77.04;Boston|MA|42.36|-71.06
Nashville|TN|36.16|-86.78;Detroit|MI|42.33|-83.05;Portland|OR|45.52|-122.68;Las Vegas|NV|36.17|-115.14
Memphis|TN|35.15|-90.05;Louisville|KY|38.25|-85.76;Baltimore|MD|39.29|-76.61;Milwaukee|WI|43.04|-87.91
Albuquerque|NM|35.08|-106.65;Tucson|AZ|32.22|-110.97;Fresno|CA|36.74|-119.79;Sacramento|CA|38.58|-121.49
Kansas City|MO|39.10|-94.58;Atlanta|GA|33.75|-84.39;Omaha|NE|41.26|-95.93;Raleigh|NC|35.78|-78.64
Miami|FL|25.76|-80.19;Cleveland|OH|41.50|-81.69;Tulsa|OK|36.15|-95.99;Oakland|CA|37.80|-122.27
Minneapolis|MN|44.98|-93.27;Tampa|FL|27.95|-82.46;New Orleans|LA|29.95|-90.07;Pittsburgh|PA|40.44|-80.00
Cincinnati|OH|39.10|-84.51;St. Louis|MO|38.63|-90.20;Orlando|FL|28.54|-81.38;Salt Lake City|UT|40.76|-111.89
Richmond|VA|37.54|-77.44;Buffalo|NY|42.89|-78.88;Hartford|CT|41.76|-72.68;Providence|RI|41.82|-71.41
Boise|ID|43.62|-116.20;Madison|WI|43.07|-89.40;Des Moines|IA|41.59|-93.62;Birmingham|AL|33.52|-86.80
Durham|NC|35.99|-78.90;Chapel Hill|NC|35.91|-79.06;Cary|NC|35.79|-78.78;Research Triangle Park|NC|35.90|-78.86
Cambridge|MA|42.37|-71.11;Waltham|MA|42.38|-71.24;Somerville|MA|42.39|-71.10;Palo Alto|CA|37.44|-122.14
Mountain View|CA|37.39|-122.08;Menlo Park|CA|37.45|-122.18;Redwood City|CA|37.49|-122.24;South San Francisco|CA|37.65|-122.41
Sunnyvale|CA|37.37|-122.04;Santa Clara|CA|37.35|-121.96;Cupertino|CA|37.32|-122.03;Berkeley|CA|37.87|-122.27
Emeryville|CA|37.83|-122.29;Irvine|CA|33.68|-117.83;Santa Monica|CA|34.02|-118.49;Pasadena|CA|34.15|-118.14
Bellevue|WA|47.61|-122.20;Redmond|WA|47.67|-122.12;Kirkland|WA|47.68|-122.21;Princeton|NJ|40.36|-74.67
Newark|NJ|40.74|-74.17;Jersey City|NJ|40.73|-74.08;Parsippany|NJ|40.86|-74.43;Bridgewater|NJ|40.59|-74.62
Summit|NJ|40.72|-74.36;Morristown|NJ|40.80|-74.48;Stamford|CT|41.05|-73.54;White Plains|NY|41.03|-73.76
Brooklyn|NY|40.68|-73.94;Plano|TX|33.02|-96.70;Irving|TX|32.81|-96.95;Fort Worth|TX|32.76|-97.33
Scottsdale|AZ|33.49|-111.93;Tempe|AZ|33.43|-111.94;Chandler|AZ|33.31|-111.84;Boulder|CO|40.01|-105.27
Cherry Creek|CO|39.72|-104.95;Greenwood Village|CO|39.62|-104.95;Ann Arbor|MI|42.28|-83.74;Troy|MI|42.61|-83.15
Dearborn|MI|42.32|-83.18;Evanston|IL|42.05|-87.69;Skokie|IL|42.03|-87.73;Northbrook|IL|42.13|-87.83
Deerfield|IL|42.17|-87.84;Lake Forest|IL|42.26|-87.84;Lake Bluff|IL|42.28|-87.83;North Chicago|IL|42.33|-87.84
Waukegan|IL|42.36|-87.84;Libertyville|IL|42.28|-87.95;Mundelein|IL|42.26|-88.00;Vernon Hills|IL|42.23|-87.98
Lincolnshire|IL|42.19|-87.91;Buffalo Grove|IL|42.15|-87.96;Arlington Heights|IL|42.09|-87.98;Schaumburg|IL|42.03|-88.08
Rosemont|IL|41.99|-87.87;Des Plaines|IL|42.03|-87.88;Elk Grove Village|IL|42.00|-87.97;Itasca|IL|41.97|-88.01
Oak Brook|IL|41.84|-87.93;Lisle|IL|41.80|-88.07;Naperville|IL|41.79|-88.15;Downers Grove|IL|41.81|-88.01
Aurora|IL|41.76|-88.32;Elgin|IL|42.04|-88.28;Crystal Lake|IL|42.24|-88.32;Algonquin|IL|42.17|-88.29
Barrington|IL|42.15|-88.14;Palatine|IL|42.11|-88.03;Woodstock|IL|42.31|-88.45;McHenry|IL|42.33|-88.27
Lake Zurich|IL|42.20|-88.09;Gurnee|IL|42.37|-87.90;Highland Park|IL|42.18|-87.80;Glenview|IL|42.07|-87.79
Wheaton|IL|41.87|-88.11;Joliet|IL|41.53|-88.08;Rockford|IL|42.27|-89.09;Peoria|IL|40.69|-89.59
Springfield|IL|39.80|-89.64;Champaign|IL|40.12|-88.24;Pleasant Prairie|WI|42.52|-87.91;Kenosha|WI|42.58|-87.82
Racine|WI|42.73|-87.78;Lake Geneva|WI|42.59|-88.43;Mequon|WI|43.23|-87.98;Gary|IN|41.59|-87.35
Hammond|IN|41.58|-87.50;Merrillville|IN|41.48|-87.33;Valparaiso|IN|41.47|-87.06;South Bend|IN|41.68|-86.25
Lexington|KY|38.04|-84.50;Charleston|SC|32.78|-79.93;Greenville|SC|34.85|-82.40;Savannah|GA|32.08|-81.09
Alpharetta|GA|34.08|-84.29;Chattanooga|TN|35.05|-85.31;Knoxville|TN|35.96|-83.92;Huntsville|AL|34.73|-86.59
Wilmington|DE|39.74|-75.55;Rockville|MD|39.08|-77.15;Gaithersburg|MD|39.14|-77.20;Bethesda|MD|38.98|-77.10
Reston|VA|38.96|-77.36;Arlington|VA|38.88|-77.10;McLean|VA|38.93|-77.18;Malvern|PA|40.04|-75.51
King of Prussia|PA|40.09|-75.38;Collegeville|PA|40.19|-75.45;Horsham|PA|40.18|-75.13;Lancaster|PA|40.04|-76.31
Rahway|NJ|40.61|-74.28;Kenilworth|NJ|40.67|-74.29;Whitehouse Station|NJ|40.62|-74.77;Titusville|NJ|40.31|-74.86
Thousand Oaks|CA|34.17|-118.84;Cleveland Heights|OH|41.50|-81.56;Dublin|OH|40.10|-83.11;Honolulu|HI|21.31|-157.86
Anchorage|AK|61.22|-149.90;Oklahoma City|OK|35.47|-97.52;Little Rock|AR|34.75|-92.29;Jackson|MS|32.30|-90.18
"""


@lru_cache(maxsize=1)
def _places() -> dict:
    places: dict[tuple, tuple] = {}
    for row in _BUILTIN.replace("\n", ";").split(";"):
        row = row.strip()
        if not row:
            continue
        name, st, lat, lon = row.split("|")
        places[(name.lower(), st)] = (float(lat), float(lon))
    extra = PACKAGE_DIR / "resources" / "us_places.csv.gz"
    if extra.exists():
        try:
            with gzip.open(extra, "rt", encoding="utf-8", newline="") as f:
                for name, st, lat, lon in csv.reader(f):
                    places.setdefault((name.lower(), st), (float(lat), float(lon)))
        except (OSError, ValueError):
            pass
    return places


def _clean_city(name: str) -> str:
    n = name.lower().strip().strip(".")
    n = re.sub(r"^(saint|st)\b\.?\s*", "st. ", n) if re.match(r"^(saint|st)\b", n) else n
    return n


def lookup(city: str, state: str) -> tuple[float, float] | None:
    return _places().get((_clean_city(city), state.upper()))


_CITY_STATE = re.compile(r"([A-Za-z][A-Za-z.' -]{1,40}?),\s*([A-Za-z]{2}|[A-Za-z ]{4,20}?)(?=$|[,;(\-|/]|\s+\d|\s+united|\s+usa|\s+us\b)", re.I)
_US_DASH = re.compile(r"\bUS-([A-Z]{2})-([A-Za-z .'-]+)", re.I)


def to_state(token: str) -> str | None:
    t = token.strip().strip(".").lower()
    if len(t) == 2 and t.upper() in STATE_CODES:
        return t.upper()
    return STATES.get(t)


def parse_location(raw: str) -> dict:
    """{raw, city, state, lat, lon, remote}. Fields are None when they can't be determined."""
    text = (raw or "").strip()
    out = {"raw": text, "city": None, "state": None, "lat": None, "lon": None,
           "remote": bool(re.search(r"\bremote\b|work from home|anywhere", text, re.I))}
    m = _US_DASH.search(text)
    if m:
        out["state"], out["city"] = to_state(m.group(1)), m.group(2).strip()
    else:
        for m in _CITY_STATE.finditer(text):
            city_part = re.sub(r"^(?:remote|hybrid|on-?site)\s*[-:–—]\s*", "", m.group(1).strip(), flags=re.I)
            st = to_state(m.group(2))
            if st:
                out["city"], out["state"] = city_part.strip(" -"), st
                break
        if not out["state"]:  # "Remote - Illinois", "Illinois"
            for token in re.split(r"[,\-/|()]", text):
                st = to_state(token)
                if st:
                    out["state"] = st
                    break
    if out["city"] and out["state"]:
        coords = lookup(out["city"], out["state"])
        if coords:
            out["lat"], out["lon"] = coords
    return out


def parse_locations(raws: list[str]) -> list[dict]:
    return [parse_location(r) for r in raws if r and r.strip()]


def miles(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 3958.8 * 2 * math.asin(math.sqrt(h))


def resolve(place: str) -> tuple[float, float] | None:
    loc = parse_location(place)
    return (loc["lat"], loc["lon"]) if loc["lat"] is not None else None
