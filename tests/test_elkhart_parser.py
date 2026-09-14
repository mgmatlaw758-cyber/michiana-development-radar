from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from michiana_radar.parsers.elkhart import Page, parse_permit_pages

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "elkhart_sample_pages.json"
SOURCE_URL = (
    "https://www.elkhartcountyplanninganddevelopment.com/"
    "doc/2026/august-2026-permits.pdf"
)


def load_pages() -> list[Page]:
    raw_pages = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return [Page(number=item["page_number"], text=item["text"]) for item in raw_pages]


def test_parses_records_and_merges_continuation_pages() -> None:
    records = parse_permit_pages(
        load_pages(),
        source_url=SOURCE_URL,
        source_period="2026-08",
        commercial_buildings_only=False,
    )
    by_number = {record.permit_number: record for record in records}

    assert len(records) == 5
    record = by_number["BC-1752-2026"]
    assert record.source.pages == (47, 48)
    assert record.estimated_cost == Decimal("400000.00")
    assert record.issued_date.isoformat() == "2026-08-27"
    assert record.site_address == "14905 County Road 42"
    assert record.city == "Goshen"
    assert record.postal_code == "46528"
    assert record.township == "Clinton"
    assert record.zoning == ("A-1",)
    assert record.general_contractor == "MH Bontrager Construction"
    assert len(record.parcel_numbers) == 4


def test_commercial_filter_is_on_by_default() -> None:
    records = parse_permit_pages(
        load_pages(),
        source_url=SOURCE_URL,
        source_period="2026-08",
    )

    assert records
    assert all(record.raw_permit_type.startswith("Building (C)") for record in records)
    assert "BR-1834-2026" not in {record.permit_number for record in records}


def test_noncommercial_record_is_hidden_and_personal_contact_data_is_dropped() -> None:
    records = parse_permit_pages(
        load_pages(),
        source_url=SOURCE_URL,
        source_period="2026-08",
        commercial_buildings_only=False,
    )
    residential = next(
        record for record in records if record.permit_number == "BR-1834-2026"
    )
    serialized = json.dumps(residential.to_dict())

    assert residential.visibility == "hidden"
    assert residential.owner_business is None
    assert residential.general_contractor is None
    assert "555-0101" not in serialized
    assert "REDACTED PERSONAL OWNER" not in serialized


def test_business_owner_is_retained() -> None:
    records = parse_permit_pages(
        load_pages(),
        source_url=SOURCE_URL,
        source_period="2026-08",
    )
    office = next(record for record in records if record.permit_number == "BC-1675-2026")

    assert office.owner_business == "Biddlecome Drainage Consulting LLC"
    assert office.general_contractor == "O. A. Construction Services"
