from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from .st_joseph_sync import sync_st_joseph_year
from .sync import sync_elkhart_year

ProgressCallback = Callable[[str], None]


def sync_all_year(
    *,
    year: int,
    database_path: Path,
    cache_directory: Path = Path("build/source-cache"),
    refresh: bool = False,
    progress: ProgressCallback | None = None,
) -> dict[str, object]:
    """Synchronize every currently supported Development Radar jurisdiction."""
    if year < 2017 or year > 2100:
        raise ValueError("year must be between 2017 and 2100")

    database_path = Path(database_path)
    cache_directory = Path(cache_directory)
    sources: dict[str, dict[str, object]] = {}

    def emit(source: str, message: str) -> None:
        if progress is not None:
            progress(f"[{source}] {message}")

    try:
        emit("Elkhart", "starting synchronization")
        elkhart = sync_elkhart_year(
            year=year,
            database_path=database_path,
            cache_directory=cache_directory / "elkhart",
            refresh=refresh,
            progress=lambda message: emit("Elkhart", message),
        )
        sources["elkhart"] = {
            "status": (
                "processed"
                if int(elkhart.get("failed_report_count", 0)) == 0
                else "partial_failure"
            ),
            **elkhart,
        }
    except Exception as exc:
        sources["elkhart"] = {
            "status": "failed",
            "error": f"{type(exc).__name__}: {exc}",
        }
        emit("Elkhart", f"failed: {exc}")

    try:
        emit("St. Joseph", "starting synchronization")
        st_joseph = sync_st_joseph_year(
            year=year,
            database_path=database_path,
            cache_directory=cache_directory / "st-joseph",
            refresh=refresh,
            progress=lambda message: emit("St. Joseph", message),
        )
        sources["st_joseph"] = {
            "status": (
                "processed"
                if int(st_joseph.get("failed_report_count", 0)) == 0
                else "partial_failure"
            ),
            **st_joseph,
        }
    except Exception as exc:
        sources["st_joseph"] = {
            "status": "failed",
            "error": f"{type(exc).__name__}: {exc}",
        }
        emit("St. Joseph", f"failed: {exc}")

    failed_source_count = sum(
        1
        for source in sources.values()
        if source.get("status") in {"failed", "partial_failure"}
    )
    fully_failed_source_count = sum(
        1 for source in sources.values() if source.get("status") == "failed"
    )

    if fully_failed_source_count == len(sources):
        status = "failed"
    elif failed_source_count:
        status = "partial_failure"
    else:
        status = "processed"

    return {
        "status": status,
        "year": year,
        "database": str(database_path),
        "cache_directory": str(cache_directory),
        "source_count": len(sources),
        "failed_source_count": failed_source_count,
        "sources": sources,
    }
