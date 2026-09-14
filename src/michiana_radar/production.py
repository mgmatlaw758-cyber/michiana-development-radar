from __future__ import annotations

import os
import sys
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import sleep
from typing import Mapping

from .server import serve_dashboard
from .sync_all import sync_all_year


@dataclass(frozen=True, slots=True)
class ProductionConfig:
    database_path: Path
    cache_directory: Path
    host: str
    port: int
    sync_on_start: bool
    sync_interval_hours: float
    sync_year: int | None


def _bool_value(value: str, *, name: str) -> bool:
    normalized = value.strip().casefold()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be true/false or 1/0")


def load_production_config(
    environment: Mapping[str, str] | None = None,
) -> ProductionConfig:
    env = os.environ if environment is None else environment

    database_path = Path(env.get("RADAR_DATABASE", "build/radar.sqlite"))
    cache_directory = Path(env.get("RADAR_CACHE_DIR", "build/source-cache"))
    host = env.get("HOST", "0.0.0.0").strip() or "0.0.0.0"

    try:
        port = int(env.get("PORT", "8000"))
    except ValueError as exc:
        raise ValueError("PORT must be an integer") from exc
    if port < 1 or port > 65535:
        raise ValueError("PORT must be between 1 and 65535")

    sync_on_start = _bool_value(
        env.get("RADAR_SYNC_ON_START", "true"),
        name="RADAR_SYNC_ON_START",
    )

    try:
        sync_interval_hours = float(env.get("RADAR_SYNC_INTERVAL_HOURS", "24"))
    except ValueError as exc:
        raise ValueError("RADAR_SYNC_INTERVAL_HOURS must be a number") from exc
    if sync_interval_hours < 0:
        raise ValueError("RADAR_SYNC_INTERVAL_HOURS cannot be negative")

    raw_year = env.get("RADAR_SYNC_YEAR", "").strip()
    if raw_year:
        try:
            sync_year = int(raw_year)
        except ValueError as exc:
            raise ValueError("RADAR_SYNC_YEAR must be a four-digit year") from exc
        if sync_year < 2017 or sync_year > 2100:
            raise ValueError("RADAR_SYNC_YEAR must be between 2017 and 2100")
    else:
        sync_year = None

    return ProductionConfig(
        database_path=database_path,
        cache_directory=cache_directory,
        host=host,
        port=port,
        sync_on_start=sync_on_start,
        sync_interval_hours=sync_interval_hours,
        sync_year=sync_year,
    )


def _resolved_sync_year(config: ProductionConfig) -> int:
    if config.sync_year is not None:
        return config.sync_year
    return datetime.now(timezone.utc).year


def _run_sync(config: ProductionConfig, *, reason: str) -> bool:
    year = _resolved_sync_year(config)
    print(f"[production] {reason}: syncing Development Radar for {year}")
    try:
        result = sync_all_year(
            year=year,
            database_path=config.database_path,
            cache_directory=config.cache_directory,
            progress=lambda message: print(message, file=sys.stderr),
        )
    except Exception as exc:
        print(f"[production] sync failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return False

    status = str(result.get("status", "unknown"))
    print(f"[production] sync completed with status={status}")
    return status != "failed"


def _sync_loop(config: ProductionConfig) -> None:
    interval_seconds = config.sync_interval_hours * 3600
    while interval_seconds > 0:
        sleep(interval_seconds)
        _run_sync(config, reason="scheduled refresh")


def main() -> int:
    try:
        config = load_production_config()
    except ValueError as exc:
        print(f"production configuration error: {exc}", file=sys.stderr)
        return 2

    config.database_path.parent.mkdir(parents=True, exist_ok=True)
    config.cache_directory.mkdir(parents=True, exist_ok=True)

    database_missing = not config.database_path.is_file()
    if config.sync_on_start or database_missing:
        _run_sync(
            config,
            reason="initial refresh" if database_missing else "startup refresh",
        )

    if not config.database_path.is_file():
        print(
            "production startup failed: no Radar database exists after synchronization",
            file=sys.stderr,
        )
        return 1

    if config.sync_interval_hours > 0:
        thread = threading.Thread(
            target=_sync_loop,
            args=(config,),
            name="radar-sync",
            daemon=True,
        )
        thread.start()
        print(
            "[production] automatic refresh interval: "
            f"{config.sync_interval_hours:g} hours"
        )
    else:
        print("[production] automatic refresh disabled")

    try:
        serve_dashboard(
            config.database_path,
            host=config.host,
            port=config.port,
        )
    except (FileNotFoundError, ValueError, OSError) as exc:
        print(f"production server failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
