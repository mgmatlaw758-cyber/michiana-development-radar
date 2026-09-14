from pathlib import Path

import pytest

from michiana_radar.production import load_production_config


def test_production_config_defaults() -> None:
    config = load_production_config({})

    assert config.database_path == Path("build/radar.sqlite")
    assert config.cache_directory == Path("build/source-cache")
    assert config.host == "0.0.0.0"
    assert config.port == 8000
    assert config.sync_on_start is True
    assert config.sync_interval_hours == 24
    assert config.sync_year is None


def test_production_config_reads_environment() -> None:
    config = load_production_config(
        {
            "RADAR_DATABASE": "/data/radar.sqlite",
            "RADAR_CACHE_DIR": "/data/source-cache",
            "HOST": "0.0.0.0",
            "PORT": "9123",
            "RADAR_SYNC_ON_START": "false",
            "RADAR_SYNC_INTERVAL_HOURS": "6.5",
            "RADAR_SYNC_YEAR": "2026",
        }
    )

    assert config.database_path == Path("/data/radar.sqlite")
    assert config.cache_directory == Path("/data/source-cache")
    assert config.port == 9123
    assert config.sync_on_start is False
    assert config.sync_interval_hours == 6.5
    assert config.sync_year == 2026


def test_production_config_rejects_invalid_values() -> None:
    with pytest.raises(ValueError, match="PORT"):
        load_production_config({"PORT": "banana"})

    with pytest.raises(ValueError, match="RADAR_SYNC_ON_START"):
        load_production_config({"RADAR_SYNC_ON_START": "sometimes"})

    with pytest.raises(ValueError, match="RADAR_SYNC_INTERVAL_HOURS"):
        load_production_config({"RADAR_SYNC_INTERVAL_HOURS": "-1"})

    with pytest.raises(ValueError, match="RADAR_SYNC_YEAR"):
        load_production_config({"RADAR_SYNC_YEAR": "1999"})
