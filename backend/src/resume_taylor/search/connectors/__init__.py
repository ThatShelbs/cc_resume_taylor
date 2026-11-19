"""One module per job source. Each exposes:

    NAME                          the `ats` value stored in a company route
    list_jobs(client, route, company, queries) -> list[posting]
    hydrate(client, route, posting) -> posting     (fetch the full description if the list lacked it)
    verify(client, route, posting) -> bool | None  (is it still live? None = could not tell)

A route is a small dict, e.g. {"ats": "greenhouse", "token": "acme"}. Postings follow
`normalize.new_posting`. Connectors never raise on network trouble; they return what they got."""

from . import (
    ashby,
    bamboohr,
    breezy,
    careers_page,
    eightfold,
    greenhouse,
    lever,
    recruitee,
    rippling,
    roberthalf,
    smartrecruiters,
    teamtailor,
    workable,
    workday,
)

CONNECTORS = {
    m.NAME: m
    for m in (greenhouse, lever, ashby, workday, smartrecruiters, workable, eightfold, recruitee, bamboohr, teamtailor,
              breezy, rippling, careers_page, roberthalf)
}

# ATS boards with a public JSON list: an empty list is still a valid board (the company is just not hiring).
EMPTY_OK = ("greenhouse", "lever", "ashby", "workable", "smartrecruiters", "recruitee", "bamboohr", "teamtailor", "breezy",
            "rippling")


def connector_for(route: dict):
    return CONNECTORS.get((route or {}).get("ats", ""))
