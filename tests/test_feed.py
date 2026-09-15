from __future__ import annotations

import json
from pathlib import Path

import pytest

import michiana_radar.cli as cli_module
from michiana_radar.feed import get_project, query_project_feed
from michiana_radar.server import render_project_page
from michiana_radar.parsers.elkhart import Page, parse_permit_pages
from michiana_radar.storage import import_records

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "elkhart_sample_pages.json"
SOURCE_URL = (
    "https://www.elkhartcountyplanninganddevelopment.com/"
    "doc/2026/august-2026-permits.pdf"
)


def build_database(tmp_path: Path) -> Path:
    raw_pages = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    pages = [
        Page(number=item["page_number"], text=item["text"])
        for item in raw_pages
    ]
    records = parse_permit_pages(
        pages,
        source_url=SOURCE_URL,
        source_period="2026-08",
    )
    database_path = tmp_path / "radar.sqlite"
    import_records(
        database_path,
        records,
        jurisdiction="Elkhart County",
        source_url=SOURCE_URL,
        source_period="2026-08",
        input_file="august-2026-permits.pdf",
    )
    return database_path


def test_feed_summarizes_and_groups_stored_projects(tmp_path: Path) -> None:
    payload = query_project_feed(build_database(tmp_path))

    assert payload["summary"] == {
        "project_count": 3,
        "permit_count": 4,
        "listed_value_total": "1250000.00",
        "latest_issued_date": "2026-08-28",
    }
    assert payload["result_count"] == 3
    assert payload["returned_count"] == 3
    assert payload["facets"]["jurisdictions"] == ["Elkhart County"]
    assert payload["facets"]["cities"] == ["Goshen"]
    assert payload["facets"]["project_types"] == ["New building"]

    first = payload["projects"][0]
    assert first["jurisdiction"] == "Elkhart County"
    assert first["permit_count"] == 2
    assert first["listed_permit_value_total"] == "520000.00"
    assert first["permit_numbers"] == ["BC-0471-2026", "BC-0469-2026"]


def test_feed_searches_and_filters_projects(tmp_path: Path) -> None:
    database_path = build_database(tmp_path)

    jurisdiction_match = query_project_feed(
        database_path,
        jurisdiction="Elkhart County",
    )
    assert jurisdiction_match["result_count"] == 3

    jurisdiction_miss = query_project_feed(
        database_path,
        jurisdiction="St. Joseph County",
    )
    assert jurisdiction_miss["result_count"] == 0

    contractor_match = query_project_feed(
        database_path,
        search="clinton builders",
    )
    assert contractor_match["result_count"] == 1
    assert contractor_match["projects"][0]["permit_count"] == 2

    value_match = query_project_feed(
        database_path,
        min_value="450000",
        sort="value_desc",
    )
    assert value_match["result_count"] == 1
    assert value_match["projects"][0]["permit_numbers"] == [
        "BC-0471-2026",
        "BC-0469-2026",
    ]
    assert value_match["filtered_summary"]["project_count"] == 1
    assert (
        value_match["filtered_summary"]["listed_value_total"]
        == "520000.00"
    )

    permit_match = query_project_feed(
        database_path,
        search="BC-1675-2026",
    )
    assert permit_match["result_count"] == 1
    assert permit_match["projects"][0]["site_address"] == (
        "21960 County Road 45"
    )


def test_feed_does_not_reintroduce_contact_or_personal_owner_data(
    tmp_path: Path,
) -> None:
    serialized = json.dumps(query_project_feed(build_database(tmp_path)))

    assert "555-010" not in serialized
    assert "REDACTED PERSONAL OWNER" not in serialized
    assert "MH Bontrager Construction" in serialized


def test_cli_dispatches_serve_command(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "radar.sqlite"
    database_path.write_bytes(b"database fixture")
    called = {}

    def fake_serve(database, *, host, port):
        called.update(database=database, host=host, port=port)

    monkeypatch.setattr(cli_module, "serve_dashboard", fake_serve)

    exit_code = cli_module.main(
        [
            "serve",
            "--database",
            str(database_path),
            "--port",
            "8765",
        ]
    )

    assert exit_code == 0
    assert called == {
        "database": database_path,
        "host": "127.0.0.1",
        "port": 8765,
    }


def test_project_lookup_returns_one_exact_project(tmp_path: Path) -> None:
    database_path = build_database(tmp_path)
    feed = query_project_feed(database_path)
    project_id = feed["projects"][0]["project_id"]

    project = get_project(database_path, project_id)

    assert project["project_id"] == project_id
    assert project["permit_count"] == 2

    with pytest.raises(ValueError, match="Invalid project ID"):
        get_project(database_path, "../radar.sqlite")
    with pytest.raises(KeyError, match="Project not found"):
        get_project(database_path, "project-00000000000000")


def test_project_page_links_to_exact_source_pages(tmp_path: Path) -> None:
    database_path = build_database(tmp_path)
    project_id = query_project_feed(database_path)["projects"][0]["project_id"]

    html = render_project_page(get_project(database_path, project_id))

    assert "BC-0469-2026" in html
    assert "BC-0471-2026" in html
    assert "#page=18" in html
    assert "#page=119" in html
    assert "555-010" not in html
    assert "REDACTED PERSONAL OWNER" not in html
