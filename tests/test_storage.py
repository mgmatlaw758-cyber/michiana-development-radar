from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path

from michiana_radar.grouping import group_permits
from michiana_radar.models import SourceRef
from michiana_radar.parsers.elkhart import Page, parse_permit_pages
from michiana_radar.storage import import_records, load_permits

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "elkhart_sample_pages.json"
SOURCE_URL = (
    "https://www.elkhartcountyplanninganddevelopment.com/"
    "doc/2026/august-2026-permits.pdf"
)


def load_commercial_records():
    raw_pages = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    pages = [
        Page(number=item["page_number"], text=item["text"])
        for item in raw_pages
    ]
    return parse_permit_pages(
        pages,
        source_url=SOURCE_URL,
        source_period="2026-08",
    )


def test_import_is_idempotent_and_updates_changed_records(tmp_path: Path) -> None:
    database_path = tmp_path / "nested" / "radar.sqlite"
    records = load_commercial_records()

    first = import_records(
        database_path,
        records,
        jurisdiction="Elkhart County",
        source_url=SOURCE_URL,
        source_period="2026-08",
        input_file="august-2026-permits.pdf",
    )

    assert database_path.exists()
    assert first.inserted_count == len(records)
    assert first.updated_count == 0
    assert first.unchanged_count == 0
    assert first.stored_permit_count == len(records)
    assert first.stored_project_count == len(group_permits(records))

    second = import_records(
        database_path,
        records,
        jurisdiction="Elkhart County",
        source_url=SOURCE_URL,
        source_period="2026-08",
        input_file="august-2026-permits.pdf",
    )

    assert second.inserted_count == 0
    assert second.updated_count == 0
    assert second.unchanged_count == len(records)
    assert second.stored_permit_count == len(records)

    changed_records = [
        replace(records[0], estimated_cost=Decimal("123456.00")),
        *records[1:],
    ]
    third = import_records(
        database_path,
        changed_records,
        jurisdiction="Elkhart County",
        source_url=SOURCE_URL,
        source_period="2026-08",
        input_file="august-2026-permits.pdf",
    )

    assert third.inserted_count == 0
    assert third.updated_count == 1
    assert third.unchanged_count == len(records) - 1

    stored = {
        record.permit_number: record
        for record in load_permits(database_path)
    }
    assert (
        stored[changed_records[0].permit_number].estimated_cost
        == Decimal("123456.00")
    )

    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM permit_sources"
        ).fetchone()[0] == len(records)
        assert connection.execute(
            "SELECT COUNT(*) FROM import_runs"
        ).fetchone()[0] == 3


def test_projects_are_rebuilt_across_monthly_imports(tmp_path: Path) -> None:
    database_path = tmp_path / "radar.sqlite"
    base = load_commercial_records()[0]

    june_permit = replace(
        base,
        permit_number="BC-1003-2026",
        issued_date=date(2026, 6, 19),
        description="Addition to existing warehouse for D&M Sales",
        site_address="13487 County Road 22",
        parcel_numbers=("20-08-16-401-016.000-034",),
        source=SourceRef(
            url=(
                "https://www.elkhartcountyplanninganddevelopment.com/"
                "doc/2026/june-2026-permits.pdf"
            ),
            period="2026-06",
            pages=(205,),
        ),
    )
    august_permit = replace(
        base,
        permit_number="BC-1682-2026",
        issued_date=date(2026, 8, 19),
        description=(
            "Addition currently being built; see permit BC-1003-2026"
        ),
        site_address="13487 County Road 22",
        parcel_numbers=(
            "20-08-16-401-016.000-034",
            "20-08-16-401-023.000-034",
        ),
        source=SourceRef(
            url=(
                "https://www.elkhartcountyplanninganddevelopment.com/"
                "doc/2026/august-2026-permits.pdf"
            ),
            period="2026-08",
            pages=(199,),
        ),
    )

    first = import_records(
        database_path,
        [june_permit],
        jurisdiction="Elkhart County",
        source_url=june_permit.source.url,
        source_period="2026-06",
        input_file="june-2026-permits.pdf",
    )
    with sqlite3.connect(database_path) as connection:
        first_project_id = connection.execute(
            "SELECT project_id FROM projects"
        ).fetchone()[0]

    second = import_records(
        database_path,
        [august_permit],
        jurisdiction="Elkhart County",
        source_url=august_permit.source.url,
        source_period="2026-08",
        input_file="august-2026-permits.pdf",
    )

    assert first.stored_project_count == 1
    assert second.stored_permit_count == 2
    assert second.stored_project_count == 1

    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            """
            SELECT permits.permit_number
            FROM project_permits
            JOIN permits USING (record_id)
            ORDER BY permits.permit_number
            """
        ).fetchall()
        rebuilt_project_id = connection.execute(
            "SELECT project_id FROM projects"
        ).fetchone()[0]

    assert rows == [("BC-1003-2026",), ("BC-1682-2026",)]
    assert rebuilt_project_id == first_project_id
