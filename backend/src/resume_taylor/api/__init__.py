"""
Resume Taylor's HTTP API: a FastAPI backend over the resume pipeline.

The API never tailors anything itself. It keeps the pipeline's canonical inputs
(in_profile*.docx, in_resume*.docx, fact_bank.yaml, do_not_claim.txt) in the exact
layout the pipeline parses, stores one folder per job application under projects/,
and runs the pipeline as a subprocess for every generation or re-render. The
tailoring rules still live only in .claude/skills/.

    main.py       create_app(): wires everything together
    context.py    shared per-app state and helpers (injected into routes as `Ctx`)
    schemas.py    request bodies
    uploads.py    reading and validating file uploads
    security.py   loopback-only host check and the per-launch token
    errors.py     domain errors -> HTTP responses
    spa.py        serves the built React app (frontend/dist)
    routers/      the HTTP API, one module per area (each declares its own prefix)
    services/     background jobs, pipeline runner, live checks, sample data, OS integration
    storage/      files on disk: paths, projects, profile, resume ingest, facts, settings, ...
"""
