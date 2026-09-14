from __future__ import annotations

from pathlib import Path

import michiana_radar.sync_all as sync_all_module


def test_sync_all_runs_both_sources(monkeypatch, tmp_path: Path) -> None:
    calls: list[tuple[str, Path]] = []

    def fake_elkhart(**kwargs):
        calls.append(("elkhart", kwargs["cache_directory"]))
        return {"failed_report_count": 0, "processed_report_count": 8}

    def fake_st_joseph(**kwargs):
        calls.append(("st_joseph", kwargs["cache_directory"]))
        return {"failed_report_count": 0, "processed_report_count": 7}

    monkeypatch.setattr(sync_all_module, "sync_elkhart_year", fake_elkhart)
    monkeypatch.setattr(sync_all_module, "sync_st_joseph_year", fake_st_joseph)

    payload = sync_all_module.sync_all_year(
        year=2026,
        database_path=tmp_path / "radar.sqlite",
        cache_directory=tmp_path / "cache",
    )

    assert payload["status"] == "processed"
    assert payload["failed_source_count"] == 0
    assert calls == [
        ("elkhart", tmp_path / "cache" / "elkhart"),
        ("st_joseph", tmp_path / "cache" / "st-joseph"),
    ]
    assert payload["sources"]["elkhart"]["processed_report_count"] == 8
    assert payload["sources"]["st_joseph"]["processed_report_count"] == 7


def test_sync_all_continues_when_one_source_fails(monkeypatch, tmp_path: Path) -> None:
    def fake_elkhart(**kwargs):
        raise RuntimeError("county site unavailable")

    def fake_st_joseph(**kwargs):
        return {"failed_report_count": 0, "processed_report_count": 7}

    monkeypatch.setattr(sync_all_module, "sync_elkhart_year", fake_elkhart)
    monkeypatch.setattr(sync_all_module, "sync_st_joseph_year", fake_st_joseph)

    payload = sync_all_module.sync_all_year(
        year=2026,
        database_path=tmp_path / "radar.sqlite",
    )

    assert payload["status"] == "partial_failure"
    assert payload["failed_source_count"] == 1
    assert payload["sources"]["elkhart"]["status"] == "failed"
    assert "county site unavailable" in payload["sources"]["elkhart"]["error"]
    assert payload["sources"]["st_joseph"]["status"] == "processed"


def test_sync_all_marks_report_level_failure(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        sync_all_module,
        "sync_elkhart_year",
        lambda **kwargs: {"failed_report_count": 1, "processed_report_count": 7},
    )
    monkeypatch.setattr(
        sync_all_module,
        "sync_st_joseph_year",
        lambda **kwargs: {"failed_report_count": 0, "processed_report_count": 7},
    )

    payload = sync_all_module.sync_all_year(
        year=2026,
        database_path=tmp_path / "radar.sqlite",
    )

    assert payload["status"] == "partial_failure"
    assert payload["failed_source_count"] == 1
    assert payload["sources"]["elkhart"]["status"] == "partial_failure"
