from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

import michiana_radar.cli as cli_module
import michiana_radar.sync as sync_module
from michiana_radar.parsers.elkhart import Page
from michiana_radar.sync import (
    PermitExport,
    discover_exports_from_html,
    download_export,
    sync_elkhart_year,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "elkhart_sample_pages.json"
SOURCE_PAGE_URL = (
    "https://www.elkhartcountyplanninganddevelopment.com/Building.html"
)


def load_pages() -> list[Page]:
    raw_pages = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return [
        Page(number=item["page_number"], text=item["text"])
        for item in raw_pages
    ]


def test_discovers_sorted_official_exports_for_selected_year() -> None:
    html = """
    <a href="/doc/2026/august-2026-permits.pdf">
      Building Permits - <span>August 2026</span>
    </a>
    <a href="/doc/2025/december-2025-permits.pdf">
      Building Permits - December 2025
    </a>
    <a href="https://evil.example/february.pdf">
      Building Permits - February 2026
    </a>
    <a href="/doc/2026/january-2026-permits.pdf">
      Building Permits - January 2026
    </a>
    <a href="/doc/2026/stats.pdf">Building Stats Report - March 2026</a>
    """

    exports = discover_exports_from_html(
        html,
        year=2026,
        source_page_url=SOURCE_PAGE_URL,
    )

    assert [(export.month, export.period) for export in exports] == [
        (1, "2026-01"),
        (8, "2026-08"),
    ]
    assert exports[0].source_url == (
        "https://www.elkhartcountyplanninganddevelopment.com/"
        "doc/2026/january-2026-permits.pdf"
    )


def test_download_uses_a_valid_cached_pdf(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "cached.pdf"
    target.write_bytes(b"%PDF-1.7\ncached fixture")
    export = PermitExport(
        year=2026,
        month=8,
        month_name="August",
        source_url=(
            "https://www.elkhartcountyplanninganddevelopment.com/"
            "doc/2026/august-2026-permits.pdf"
        ),
    )

    def fail_if_called(*args, **kwargs):
        raise AssertionError("network should not be called for a valid cache")

    monkeypatch.setattr(sync_module, "urlopen", fail_if_called)

    assert download_export(export, target) == "cached"


def test_download_rejects_an_official_looking_offsite_link(
    tmp_path: Path,
) -> None:
    export = PermitExport(
        year=2026,
        month=8,
        month_name="August",
        source_url="https://evil.example/august-2026-permits.pdf",
    )

    with pytest.raises(ValueError, match="non-official"):
        download_export(export, tmp_path / "report.pdf")


def test_year_sync_imports_in_order_and_reuses_existing_records(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exports = [
        PermitExport(
            year=2026,
            month=1,
            month_name="January",
            source_url=(
                "https://www.elkhartcountyplanninganddevelopment.com/"
                "doc/2026/january-2026-permits.pdf"
            ),
        ),
        PermitExport(
            year=2026,
            month=2,
            month_name="February",
            source_url=(
                "https://www.elkhartcountyplanninganddevelopment.com/"
                "doc/2026/february-2026-permits.pdf"
            ),
        ),
    ]

    monkeypatch.setattr(
        sync_module,
        "discover_elkhart_exports",
        lambda year, source_page_url: exports,
    )
    monkeypatch.setattr(
        sync_module,
        "download_export",
        lambda export, target, refresh=False: "cached",
    )
    monkeypatch.setattr(
        sync_module,
        "extract_pdf_pages",
        lambda target: load_pages(),
    )

    messages: list[str] = []
    database_path = tmp_path / "radar.sqlite"
    payload = sync_elkhart_year(
        year=2026,
        database_path=database_path,
        cache_directory=tmp_path / "cache",
        progress=messages.append,
    )

    assert payload["processed_report_count"] == 2
    assert payload["failed_report_count"] == 0
    assert payload["totals"] == {
        "input_permit_count": 8,
        "inserted_count": 4,
        "updated_count": 0,
        "unchanged_count": 4,
        "stored_permit_count": 4,
        "stored_project_count": 3,
    }
    assert messages[0].startswith("2026-01")

    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM permit_sources"
        ).fetchone()[0] == 8


def test_cli_dispatches_sync_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_path = tmp_path / "summary.json"
    expected = {
        "failed_report_count": 0,
        "processed_report_count": 8,
    }

    def fake_sync(**kwargs):
        assert kwargs["year"] == 2026
        assert kwargs["database_path"] == tmp_path / "radar.sqlite"
        return expected

    monkeypatch.setattr(cli_module, "sync_elkhart_year", fake_sync)

    exit_code = cli_module.main(
        [
            "sync-elkhart",
            "--year",
            "2026",
            "--database",
            str(tmp_path / "radar.sqlite"),
            "--output",
            str(output_path),
        ]
    )

    assert exit_code == 0
    assert json.loads(output_path.read_text(encoding="utf-8")) == expected
