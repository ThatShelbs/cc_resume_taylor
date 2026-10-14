"""`python -m resume_taylor.api.storage.resume_ingest --ai FILE --out JSON`: structure a
resume with one Claude call. The API runs this as a job when the parser finds no employers."""

import argparse
import sys
from pathlib import Path

from resume_taylor.pipeline.runtime import stage

from .ai import ai_parse
from .extract import extract_text
from .models import IngestError
from .verify import verify


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Structure an uploaded resume with one Claude call.")
    parser.add_argument("--ai", type=Path, required=True, help="uploaded .pdf/.docx")
    parser.add_argument("--out", type=Path, required=True, help="where to write the structure JSON")
    args = parser.parse_args(argv)
    stage("preparing")
    print(f"Reading {args.ai.name}...")
    try:
        text = extract_text(args.ai)
        stage("drafting")
        print("Asking Claude to structure the resume (verbatim extraction only)...")
        structure = ai_parse(text)
    except IngestError as exc:
        sys.exit(str(exc))
    stage("validating")
    structure.raw_text = text
    structure.source_file = args.ai.name
    verify(structure, text)
    print(f"Found {len(structure.jobs)} employer entries; {len(structure.flags)} field(s) flagged for review.")
    args.out.write_text(structure.model_dump_json(indent=2), encoding="utf-8")
    stage("done")


if __name__ == "__main__":
    main()
