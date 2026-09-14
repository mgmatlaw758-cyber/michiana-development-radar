from __future__ import annotations

import hashlib
import json
from collections import Counter
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Iterable, cast

from .grouping import group_permits
from .models import PermitRecord, SourceRef, Visibility

SCHEMA_VERSION = 1

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS permits (
    record_id TEXT PRIMARY KEY,
    jurisdiction TEXT NOT NULL,
    permit_number TEXT NOT NULL,
    raw_permit_type TEXT NOT NULL,
    project_category TEXT NOT NULL,
    project_type TEXT NOT NULL,
    issued_date TEXT,
    estimated_cost TEXT,
    description TEXT NOT NULL,
    site_address TEXT NOT NULL,
    city TEXT NOT NULL,
    state TEXT NOT NULL,
    postal_code TEXT NOT NULL,
    township TEXT NOT NULL,
    zoning_json TEXT NOT NULL,
    owner_business TEXT,
    general_contractor TEXT,
    parcel_numbers_json TEXT NOT NULL,
    source_url TEXT NOT NULL,
    source_period TEXT,
    source_pages_json TEXT NOT NULL,
    visibility TEXT NOT NULL
        CHECK (visibility IN ('business_intelligence', 'hidden')),
    content_hash TEXT NOT NULL,
    first_imported_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    UNIQUE (jurisdiction, permit_number)
);

CREATE INDEX IF NOT EXISTS permits_issued_date_idx
    ON permits (issued_date);
CREATE INDEX IF NOT EXISTS permits_source_period_idx
    ON permits (source_period);
CREATE INDEX IF NOT EXISTS permits_general_contractor_idx
    ON permits (general_contractor);

CREATE TABLE IF NOT EXISTS permit_sources (
    record_id TEXT NOT NULL
        REFERENCES permits (record_id) ON DELETE CASCADE,
    source_url TEXT NOT NULL,
    source_period TEXT NOT NULL,
    source_pages_json TEXT NOT NULL,
    input_file TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    PRIMARY KEY (record_id, source_url, source_period)
);

CREATE TABLE IF NOT EXISTS projects (
    project_id TEXT PRIMARY KEY,
    grouping_status TEXT NOT NULL,
    listed_permit_value_total TEXT NOT NULL,
    max_listed_permit_value TEXT NOT NULL,
    rebuilt_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS project_permits (
    project_id TEXT NOT NULL
        REFERENCES projects (project_id) ON DELETE CASCADE,
    record_id TEXT NOT NULL
        REFERENCES permits (record_id) ON DELETE CASCADE,
    PRIMARY KEY (project_id, record_id),
    UNIQUE (record_id)
);

CREATE TABLE IF NOT EXISTS import_runs (
    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
    jurisdiction TEXT NOT NULL,
    source_url TEXT NOT NULL,
    source_period TEXT,
    input_file TEXT NOT NULL,
    input_permit_count INTEGER NOT NULL,
    inserted_count INTEGER NOT NULL,
    updated_count INTEGER NOT NULL,
    unchanged_count INTEGER NOT NULL,
    stored_permit_count INTEGER NOT NULL,
    stored_project_count INTEGER NOT NULL,
    imported_at TEXT NOT NULL
);

PRAGMA user_version = 1;
"""

INSERT_PERMIT_SQL = """
INSERT INTO permits (
    record_id,
    jurisdiction,
    permit_number,
    raw_permit_type,
    project_category,
    project_type,
    issued_date,
    estimated_cost,
    description,
    site_address,
    city,
    state,
    postal_code,
    township,
    zoning_json,
    owner_business,
    general_contractor,
    parcel_numbers_json,
    source_url,
    source_period,
    source_pages_json,
    visibility,
    content_hash,
    first_imported_at,
    last_seen_at
) VALUES (
    :record_id,
    :jurisdiction,
    :permit_number,
    :raw_permit_type,
    :project_category,
    :project_type,
    :issued_date,
    :estimated_cost,
    :description,
    :site_address,
    :city,
    :state,
    :postal_code,
    :township,
    :zoning_json,
    :owner_business,
    :general_contractor,
    :parcel_numbers_json,
    :source_url,
    :source_period,
    :source_pages_json,
    :visibility,
    :content_hash,
    :first_imported_at,
    :last_seen_at
)
"""

UPDATE_PERMIT_SQL = """
UPDATE permits
SET
    jurisdiction = :jurisdiction,
    permit_number = :permit_number,
    raw_permit_type = :raw_permit_type,
    project_category = :project_category,
    project_type = :project_type,
    issued_date = :issued_date,
    estimated_cost = :estimated_cost,
    description = :description,
    site_address = :site_address,
    city = :city,
    state = :state,
    postal_code = :postal_code,
    township = :township,
    zoning_json = :zoning_json,
    owner_business = :owner_business,
    general_contractor = :general_contractor,
    parcel_numbers_json = :parcel_numbers_json,
    source_url = :source_url,
    source_period = :source_period,
    source_pages_json = :source_pages_json,
    visibility = :visibility,
    content_hash = :content_hash,
    last_seen_at = :last_seen_at
WHERE record_id = :record_id
"""


@dataclass(frozen=True, slots=True)
class ImportSummary:
    run_id: int
    input_permit_count: int
    inserted_count: int
    updated_count: int
    unchanged_count: int
    stored_permit_count: int
    stored_project_count: int

    def to_dict(self) -> dict[str, int]:
        return {
            "run_id": self.run_id,
            "input_permit_count": self.input_permit_count,
            "inserted_count": self.inserted_count,
            "updated_count": self.updated_count,
            "unchanged_count": self.unchanged_count,
            "stored_permit_count": self.stored_permit_count,
            "stored_project_count": self.stored_project_count,
        }


def _timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _json_list(values: Iterable[str | int]) -> str:
    return json.dumps(list(values), separators=(",", ":"))


def _content_hash(record: PermitRecord) -> str:
    payload = record.to_dict()
    payload.pop("record_id", None)
    payload.pop("source", None)
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _permit_parameters(record: PermitRecord, now: str) -> dict[str, object]:
    return {
        "record_id": record.record_id,
        "jurisdiction": record.jurisdiction,
        "permit_number": record.permit_number,
        "raw_permit_type": record.raw_permit_type,
        "project_category": record.project_category,
        "project_type": record.project_type,
        "issued_date": (
            record.issued_date.isoformat() if record.issued_date is not None else None
        ),
        "estimated_cost": (
            str(record.estimated_cost) if record.estimated_cost is not None else None
        ),
        "description": record.description,
        "site_address": record.site_address,
        "city": record.city,
        "state": record.state,
        "postal_code": record.postal_code,
        "township": record.township,
        "zoning_json": _json_list(record.zoning),
        "owner_business": record.owner_business,
        "general_contractor": record.general_contractor,
        "parcel_numbers_json": _json_list(record.parcel_numbers),
        "source_url": record.source.url,
        "source_period": record.source.period,
        "source_pages_json": _json_list(record.source.pages),
        "visibility": record.visibility,
        "content_hash": _content_hash(record),
        "first_imported_at": now,
        "last_seen_at": now,
    }


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _initialize_database(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA_SQL)
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    if version != SCHEMA_VERSION:
        raise RuntimeError(
            f"Unsupported database schema version {version}; "
            f"expected {SCHEMA_VERSION}"
        )


def _store_source_observation(
    connection: sqlite3.Connection,
    record: PermitRecord,
    *,
    input_file: str,
    now: str,
) -> None:
    connection.execute(
        """
        INSERT INTO permit_sources (
            record_id,
            source_url,
            source_period,
            source_pages_json,
            input_file,
            first_seen_at,
            last_seen_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (record_id, source_url, source_period)
        DO UPDATE SET
            source_pages_json = excluded.source_pages_json,
            input_file = excluded.input_file,
            last_seen_at = excluded.last_seen_at
        """,
        (
            record.record_id,
            record.source.url,
            record.source.period or "",
            _json_list(record.source.pages),
            input_file,
            now,
            now,
        ),
    )


def _load_permits_from_connection(
    connection: sqlite3.Connection,
    *,
    visible_only: bool = False,
) -> list[PermitRecord]:
    where_clause = (
        "WHERE visibility = 'business_intelligence'" if visible_only else ""
    )
    rows = connection.execute(
        f"""
        SELECT *
        FROM permits
        {where_clause}
        ORDER BY COALESCE(issued_date, ''), permit_number
        """
    ).fetchall()

    records: list[PermitRecord] = []
    for row in rows:
        records.append(
            PermitRecord(
                jurisdiction=row["jurisdiction"],
                permit_number=row["permit_number"],
                raw_permit_type=row["raw_permit_type"],
                project_category=row["project_category"],
                project_type=row["project_type"],
                issued_date=(
                    date.fromisoformat(row["issued_date"])
                    if row["issued_date"] is not None
                    else None
                ),
                estimated_cost=(
                    Decimal(row["estimated_cost"])
                    if row["estimated_cost"] is not None
                    else None
                ),
                description=row["description"],
                site_address=row["site_address"],
                city=row["city"],
                state=row["state"],
                postal_code=row["postal_code"],
                township=row["township"],
                zoning=tuple(json.loads(row["zoning_json"])),
                owner_business=row["owner_business"],
                general_contractor=row["general_contractor"],
                parcel_numbers=tuple(json.loads(row["parcel_numbers_json"])),
                source=SourceRef(
                    url=row["source_url"],
                    period=row["source_period"],
                    pages=tuple(json.loads(row["source_pages_json"])),
                ),
                visibility=cast(Visibility, row["visibility"]),
            )
        )
    return records


def _rebuild_projects(connection: sqlite3.Connection, *, now: str) -> int:
    projects = group_permits(
        _load_permits_from_connection(connection, visible_only=True)
    )
    previous_memberships = {
        row["record_id"]: row["project_id"]
        for row in connection.execute(
            "SELECT project_id, record_id FROM project_permits"
        ).fetchall()
    }

    connection.execute("DELETE FROM project_permits")
    connection.execute("DELETE FROM projects")

    used_project_ids: set[str] = set()
    for project in projects:
        previous_counts = Counter(
            previous_memberships[permit.record_id]
            for permit in project.permits
            if permit.record_id in previous_memberships
        )
        previous_candidates = sorted(
            previous_counts,
            key=lambda project_id: (
                -previous_counts[project_id],
                project_id,
            ),
        )
        project_id = next(
            (
                candidate
                for candidate in previous_candidates
                if candidate not in used_project_ids
            ),
            project.project_id,
        )
        used_project_ids.add(project_id)

        grouping_status = (
            "probable_companion_permits"
            if len(project.permits) > 1
            else "single_permit"
        )
        connection.execute(
            """
            INSERT INTO projects (
                project_id,
                grouping_status,
                listed_permit_value_total,
                max_listed_permit_value,
                rebuilt_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                project_id,
                grouping_status,
                str(project.listed_permit_value_total),
                str(project.max_listed_permit_value),
                now,
            ),
        )
        connection.executemany(
            """
            INSERT INTO project_permits (project_id, record_id)
            VALUES (?, ?)
            """,
            [
                (project_id, permit.record_id)
                for permit in project.permits
            ],
        )

    return len(projects)


def import_records(
    database_path: Path,
    records: Iterable[PermitRecord],
    *,
    jurisdiction: str,
    source_url: str,
    source_period: str | None,
    input_file: str,
) -> ImportSummary:
    record_list = list(records)
    record_ids = [record.record_id for record in record_list]
    if len(record_ids) != len(set(record_ids)):
        raise ValueError("Cannot import duplicate permit record IDs in one run")

    connection = _connect(Path(database_path))
    try:
        _initialize_database(connection)
        with connection:
            now = _timestamp()
            inserted_count = 0
            updated_count = 0
            unchanged_count = 0

            for record in record_list:
                parameters = _permit_parameters(record, now)
                existing = connection.execute(
                    "SELECT content_hash FROM permits WHERE record_id = ?",
                    (record.record_id,),
                ).fetchone()

                if existing is None:
                    connection.execute(INSERT_PERMIT_SQL, parameters)
                    inserted_count += 1
                elif existing["content_hash"] != parameters["content_hash"]:
                    connection.execute(UPDATE_PERMIT_SQL, parameters)
                    updated_count += 1
                else:
                    connection.execute(
                        """
                        UPDATE permits
                        SET last_seen_at = ?
                        WHERE record_id = ?
                        """,
                        (now, record.record_id),
                    )
                    unchanged_count += 1

                _store_source_observation(
                    connection,
                    record,
                    input_file=input_file,
                    now=now,
                )

            stored_project_count = _rebuild_projects(connection, now=now)
            stored_permit_count = connection.execute(
                "SELECT COUNT(*) FROM permits"
            ).fetchone()[0]

            cursor = connection.execute(
                """
                INSERT INTO import_runs (
                    jurisdiction,
                    source_url,
                    source_period,
                    input_file,
                    input_permit_count,
                    inserted_count,
                    updated_count,
                    unchanged_count,
                    stored_permit_count,
                    stored_project_count,
                    imported_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    jurisdiction,
                    source_url,
                    source_period,
                    input_file,
                    len(record_list),
                    inserted_count,
                    updated_count,
                    unchanged_count,
                    stored_permit_count,
                    stored_project_count,
                    now,
                ),
            )
            run_id = int(cursor.lastrowid)

        return ImportSummary(
            run_id=run_id,
            input_permit_count=len(record_list),
            inserted_count=inserted_count,
            updated_count=updated_count,
            unchanged_count=unchanged_count,
            stored_permit_count=stored_permit_count,
            stored_project_count=stored_project_count,
        )
    finally:
        connection.close()


def load_permits(
    database_path: Path,
    *,
    visible_only: bool = False,
) -> list[PermitRecord]:
    connection = _connect(Path(database_path))
    try:
        _initialize_database(connection)
        return _load_permits_from_connection(
            connection,
            visible_only=visible_only,
        )
    finally:
        connection.close()
