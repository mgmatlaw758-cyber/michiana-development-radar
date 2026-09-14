from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from michiana_radar.grouping import group_permits, permits_probably_share_project
from michiana_radar.parsers.elkhart import Page, parse_permit_pages

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "elkhart_sample_pages.json"
SOURCE_URL = "https://example.gov/august-2026-permits.pdf"


def load_commercial_records():
    raw_pages = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    pages = [Page(number=item["page_number"], text=item["text"]) for item in raw_pages]
    return parse_permit_pages(
        pages,
        source_url=SOURCE_URL,
        source_period="2026-08",
    )


def test_companion_permits_at_same_property_are_grouped() -> None:
    records = load_commercial_records()
    projects = group_permits(records)
    workshop = next(
        project
        for project in projects
        if "BC-0469-2026" in {permit.permit_number for permit in project.permits}
    )

    assert {permit.permit_number for permit in workshop.permits} == {
        "BC-0469-2026",
        "BC-0471-2026",
    }


def test_equal_values_alone_do_not_group_permits() -> None:
    records = load_commercial_records()
    left = next(record for record in records if record.permit_number == "BC-0469-2026")
    right = replace(
        left,
        permit_number="BC-9999-2026",
        site_address="999 Different Road",
        parcel_numbers=("20-99-99-999-999.999-999",),
    )

    assert left.estimated_cost == right.estimated_cost
    assert not permits_probably_share_project(left, right)
    assert len(group_permits([left, right])) == 2
