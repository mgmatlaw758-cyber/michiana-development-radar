from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from .grouping import group_permits
from .parsers.elkhart import parse_permit_pages
from .parsers.st_joseph import parse_commercial_report_pages
from .pdf import extract_pdf_pages
from .server import serve_dashboard
from .st_joseph_sync import (
    DEFAULT_BUILDING_PAGE_URL,
    DEFAULT_MEDIA_API_URL,
    sync_st_joseph_year,
)
from .storage import import_records
from .sync import DEFAULT_SOURCE_PAGE_URL, sync_elkhart_year
from .sync_all import sync_all_year

DEFAULT_SOURCE_URL = DEFAULT_SOURCE_PAGE_URL


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Parse an Elkhart County monthly permit PDF.",
        epilog=(
            "For automatic yearly backfills, run: "
            "michiana-radar sync-elkhart --help"
        ),
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
        "--database",
        type=Path,
        help=(
            "Upsert records into this SQLite database and rebuild projects "
            "across every stored reporting period"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Write JSON to this path instead of stdout",
    )
    return parser


def build_st_joseph_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="michiana-radar import-st-joseph",
        description=(
            "Parse and import a South Bend/St. Joseph County monthly "
            "City-County Commercial Report PDF."
        ),
    )
    parser.add_argument("pdf", type=Path, help="Downloaded commercial report PDF")
    parser.add_argument(
        "--source-url",
        required=True,
        help="Exact public South Bend source PDF URL retained with every record",
    )
    parser.add_argument(
        "--source-period",
        required=True,
        help="Reporting period in YYYY-MM format, such as 2026-08",
    )
    parser.add_argument(
        "--database",
        type=Path,
        help="Upsert records into this SQLite database",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Write JSON to this path instead of stdout",
    )
    return parser


def build_sync_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="michiana-radar sync-elkhart",
        description=(
            "Discover, download and import every published Elkhart County "
            "monthly permit export for one year."
        ),
    )
    parser.add_argument(
        "--year",
        type=int,
        required=True,
        help="Calendar year to synchronize, such as 2026",
    )
    parser.add_argument(
        "--database",
        type=Path,
        required=True,
        help="SQLite database that receives the synchronized permits",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path("build/source-cache/elkhart"),
        help="Ignored directory used for downloaded county PDFs",
    )
    parser.add_argument(
        "--source-page-url",
        default=DEFAULT_SOURCE_PAGE_URL,
        help="Official Elkhart County page containing monthly export links",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Download reports again instead of using valid cached PDFs",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Write the synchronization summary to this JSON file",
    )
    return parser


def build_st_joseph_sync_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="michiana-radar sync-st-joseph",
        description=(
            "Discover, download and import published South Bend/St. Joseph "
            "County City-County Commercial Reports for one year."
        ),
    )
    parser.add_argument(
        "--year",
        type=int,
        required=True,
        help="Report year to synchronize, such as 2026",
    )
    parser.add_argument(
        "--database",
        type=Path,
        required=True,
        help="SQLite database that receives the synchronized permits",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path("build/source-cache/st-joseph"),
        help="Ignored directory used for downloaded commercial report PDFs",
    )
    parser.add_argument(
        "--source-page-url",
        default=DEFAULT_BUILDING_PAGE_URL,
        help="Official South Bend Building Department page",
    )
    parser.add_argument(
        "--media-api-url",
        default=DEFAULT_MEDIA_API_URL,
        help="Official South Bend WordPress media API used for report discovery",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Download reports again instead of using valid cached PDFs",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Write the synchronization summary to this JSON file",
    )
    return parser


def build_sync_all_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="michiana-radar sync-all",
        description=(
            "Synchronize every currently supported Michiana Development Radar "
            "jurisdiction for one year."
        ),
    )
    parser.add_argument(
        "--year",
        type=int,
        required=True,
        help="Calendar/report year to synchronize, such as 2026",
    )
    parser.add_argument(
        "--database",
        type=Path,
        required=True,
        help="SQLite database that receives permits from every source",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path("build/source-cache"),
        help="Base ignored directory used for source PDF caches",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Download source reports again instead of using valid cached PDFs",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Write the combined synchronization summary to this JSON file",
    )
    return parser


def build_serve_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="michiana-radar serve",
        description="Open the searchable Development Radar project feed.",
    )
    parser.add_argument(
        "--database",
        type=Path,
        required=True,
        help="Existing Michiana Development Radar SQLite database",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Interface to bind to; defaults to the local machine only",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Local dashboard port; defaults to 8000",
    )
    return parser


def _write_json(payload: dict[str, object], output_path: Path | None) -> None:
    output = json.dumps(payload, indent=2, sort_keys=True)
    if output_path is None:
        print(output)
        return
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(f"{output}\n", encoding="utf-8")


def _run_parse_command(argv: Sequence[str]) -> int:
    args = build_parser().parse_args(argv)
    records = parse_permit_pages(
        extract_pdf_pages(args.pdf),
        source_url=args.source_url,
        source_period=args.source_period,
        commercial_buildings_only=not args.include_noncommercial,
    )
    projects = group_permits(records)
    payload: dict[str, object] = {
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

    if args.database:
        summary = import_records(
            args.database,
            records,
            jurisdiction="Elkhart County",
            source_url=args.source_url,
            source_period=args.source_period,
            input_file=args.pdf.name,
        )
        payload["database"] = {
            "path": str(args.database),
            **summary.to_dict(),
        }

    _write_json(payload, args.output)
    return 0


def _run_st_joseph_command(argv: Sequence[str]) -> int:
    parser = build_st_joseph_parser()
    args = parser.parse_args(argv)
    if not args.source_period or len(args.source_period) != 7:
        parser.error("source-period must use YYYY-MM")

    records = parse_commercial_report_pages(
        extract_pdf_pages(args.pdf),
        source_url=args.source_url,
        source_period=args.source_period,
    )
    projects = group_permits(records)
    payload: dict[str, object] = {
        "source": {
            "jurisdiction": "St. Joseph County",
            "url": args.source_url,
            "period": args.source_period,
            "input_file": args.pdf.name,
        },
        "permit_count": len(records),
        "probable_project_count": len(projects),
        "permits": [record.to_dict() for record in records],
        "projects": [project.to_dict() for project in projects],
    }

    if args.database:
        summary = import_records(
            args.database,
            records,
            jurisdiction="St. Joseph County",
            source_url=args.source_url,
            source_period=args.source_period,
            input_file=args.pdf.name,
        )
        payload["database"] = {
            "path": str(args.database),
            **summary.to_dict(),
        }

    _write_json(payload, args.output)
    return 0


def _run_sync_command(argv: Sequence[str]) -> int:
    parser = build_sync_parser()
    args = parser.parse_args(argv)
    if args.year < 2017 or args.year > 2100:
        parser.error("year must be between 2017 and 2100")

    try:
        payload = sync_elkhart_year(
            year=args.year,
            database_path=args.database,
            cache_directory=args.cache_dir,
            source_page_url=args.source_page_url,
            refresh=args.refresh,
            progress=lambda message: print(message, file=sys.stderr),
        )
    except Exception as exc:
        print(f"sync-elkhart failed: {exc}", file=sys.stderr)
        return 1

    _write_json(payload, args.output)
    return 1 if payload["failed_report_count"] else 0


def _run_st_joseph_sync_command(argv: Sequence[str]) -> int:
    parser = build_st_joseph_sync_parser()
    args = parser.parse_args(argv)
    if args.year < 2017 or args.year > 2100:
        parser.error("year must be between 2017 and 2100")

    try:
        payload = sync_st_joseph_year(
            year=args.year,
            database_path=args.database,
            cache_directory=args.cache_dir,
            source_page_url=args.source_page_url,
            media_api_url=args.media_api_url,
            refresh=args.refresh,
            progress=lambda message: print(message, file=sys.stderr),
        )
    except Exception as exc:
        print(f"sync-st-joseph failed: {exc}", file=sys.stderr)
        return 1

    _write_json(payload, args.output)
    return 1 if payload["failed_report_count"] else 0


def _run_sync_all_command(argv: Sequence[str]) -> int:
    parser = build_sync_all_parser()
    args = parser.parse_args(argv)
    if args.year < 2017 or args.year > 2100:
        parser.error("year must be between 2017 and 2100")

    payload = sync_all_year(
        year=args.year,
        database_path=args.database,
        cache_directory=args.cache_dir,
        refresh=args.refresh,
        progress=lambda message: print(message, file=sys.stderr),
    )
    _write_json(payload, args.output)
    return 1 if payload["failed_source_count"] else 0


def _run_serve_command(argv: Sequence[str]) -> int:
    parser = build_serve_parser()
    args = parser.parse_args(argv)
    if args.port < 1 or args.port > 65535:
        parser.error("port must be between 1 and 65535")

    try:
        serve_dashboard(
            args.database,
            host=args.host,
            port=args.port,
        )
    except (FileNotFoundError, ValueError, OSError) as exc:
        print(f"serve failed: {exc}", file=sys.stderr)
        return 1
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    raw_arguments = list(sys.argv[1:] if argv is None else argv)
    if raw_arguments[:1] == ["sync-all"]:
        return _run_sync_all_command(raw_arguments[1:])
    if raw_arguments[:1] == ["sync-elkhart"]:
        return _run_sync_command(raw_arguments[1:])
    if raw_arguments[:1] == ["sync-st-joseph"]:
        return _run_st_joseph_sync_command(raw_arguments[1:])
    if raw_arguments[:1] == ["import-st-joseph"]:
        return _run_st_joseph_command(raw_arguments[1:])
    if raw_arguments[:1] == ["serve"]:
        return _run_serve_command(raw_arguments[1:])
    return _run_parse_command(raw_arguments)


if __name__ == "__main__":
    raise SystemExit(main())
