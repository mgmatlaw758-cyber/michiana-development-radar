from __future__ import annotations

from decimal import Decimal

from michiana_radar.parsers.elkhart import Page
from michiana_radar.parsers.st_joseph import (
    parse_commercial_report_pages,
    report_period_from_pages,
)

SOURCE_URL = "https://southbendin.gov/reports/commercial-example.pdf"


def test_reads_reporting_period_from_pdf_content() -> None:
    pages = [
        Page(
            number=1,
            text="""
            COMMERCIAL REPORT
            9/1/2026
            1
            FOR THE MONTH OF AUGUST, 2026
            """,
        )
    ]

    assert report_period_from_pages(pages) == "2026-08"


def test_parses_city_county_commercial_rows() -> None:
    pages = [
        Page(
            number=1,
            text="""
            COMMERCIAL REPORT
            9/1/2026
            1
            FOR THE MONTH OF AUGUST, 2026
            BD26005459 BAKERY GROUP LLC, 1012 Riverside Dr, South Bend,
            Interior Renovation, 908 PORTAGE AVE, PORTAGE, zoned NC;
            Contractor: OWNER $115,000.00
            BD26005714 UNIVERSITY SAMPLE LLC, 724 Grace Hall, Notre Dame,
            Interior Renovation, McCourtney Hall East, PORTAGE, zoned U;
            Contractor: ZIOLKOWSKI CONSTRUCTION, INC. $1,324,276.00
            """,
        )
    ]

    records = parse_commercial_report_pages(
        pages,
        source_url=SOURCE_URL,
        source_period="2026-08",
    )

    assert len(records) == 2
    first = records[0]
    assert first.jurisdiction == "St. Joseph County"
    assert first.permit_number == "BD26005459"
    assert first.project_category == "Commercial"
    assert first.project_type == "Interior Renovation"
    assert first.estimated_cost == Decimal("115000.00")
    assert first.site_address == "908 PORTAGE AVE"
    assert first.township == "Portage"
    assert first.zoning == ("NC",)
    assert first.owner_business == "BAKERY GROUP LLC"
    assert first.general_contractor is None
    assert first.issued_date is None
    assert first.source.pages == (1,)

    second = records[1]
    assert second.estimated_cost == Decimal("1324276.00")
    assert second.general_contractor == "ZIOLKOWSKI CONSTRUCTION, INC."


def test_handles_value_split_by_pdf_text_extraction() -> None:
    pages = [
        Page(
            number=3,
            text="""
            BD26005486 $10,350,000.0
            0
            MISHAWAKA LEASING CORP, 14535 Dragoon Tr, Mishawaka,
            Building Addition and Renovation, 14535 DRAGOON TRL, PENN,
            zoned I; Contractor: DJ CONSTRUCTION COMPANY, INC.
            """,
        )
    ]

    records = parse_commercial_report_pages(
        pages,
        source_url=SOURCE_URL,
        source_period="2026-08",
    )

    assert len(records) == 1
    record = records[0]
    assert record.estimated_cost == Decimal("10350000.00")
    assert record.project_type == "Building Addition and Renovation"
    assert record.site_address == "14535 DRAGOON TRL"
    assert record.township == "Penn"
    assert record.owner_business == "MISHAWAKA LEASING CORP"
    assert record.general_contractor == "DJ CONSTRUCTION COMPANY, INC."


def test_description_can_contain_commas() -> None:
    pages = [
        Page(
            number=2,
            text="""
            BD26006123 LASALLE PARK HOMES LLC, 120 S Falcon, SOUTH BEND,
            SIDING FOR BUILDINGS 15,16, AND 19, 102 Falcon, PORTAGE,
            zoned U3; Contractor: EXCLUSIVE EXTERIORS LLC $964,392.61
            """,
        )
    ]

    records = parse_commercial_report_pages(
        pages,
        source_url=SOURCE_URL,
        source_period="2026-08",
    )

    assert len(records) == 1
    record = records[0]
    assert record.project_type == "SIDING FOR BUILDINGS 15, 16, AND 19"
    assert record.site_address == "102 Falcon"
    assert record.township == "Portage"
