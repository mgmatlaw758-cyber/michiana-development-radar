from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from pypdf import PdfReader

from .grouping import group_permits
from .parsers.elkhart import Page, parse_permit_pages

DEFAULT_SOURCE_URL = (
    "https://www.elkhartcountyplanninganddevelopment.com/Building.html"
)


def extract_pdf_pages(path: Path) -> list[Page]:
    reader = PdfReader(path)
    return [
        Page(number=index, text=page.extract_text() or "")
        for index, page in enumerate(reader.pages, start=1)
    ]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Parse an Elkhart County monthly permit PDF."
    )
    parser.add_argument("pdf", type=Path, help="Downloaded county permit PDF")
    parser.add_argument(
        "--source-url",
        default=DEFAULT_SOURCE_URL,
        help="Exact public source URL retained in exported records",
    )
    parser.add_argument(
        "--source-period",
        help="Reporting period in YYYY-MM format, such as 2026-08",
    )
    parser.add_argument(
        "--include-noncommercial",
        action="store_true",
        help="Include hidden noncommercial records for parser QA",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Write JSON to this path instead of stdout",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    records = parse_permit_pages(
        extract_pdf_pages(args.pdf),
        source_url=args.source_url,
        source_period=args.source_period,
        commercial_buildings_only=not args.include_noncommercial,
    )
    projects = group_permits(records)
    payload = {
        "source": {
            "url": args.source_url,
            "period": args.source_period,
            "input_file": args.pdf.name,
        },
        "permit_count": len(records),
        "probable_project_count": len(projects),
        "permits": [record.to_dict() for record in records],
        "projects": [project.to_dict() for project in projects],
    }
    output = json.dumps(payload, indent=2, sort_keys=True)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(f"{output}\n", encoding="utf-8")
    else:
        print(output)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
