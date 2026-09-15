from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

VALID_SORTS = frozenset(
    {"newest", "oldest", "value_desc", "value_asc", "discovered_desc"}
)
PROJECT_ID_RE = re.compile(r"^project-[0-9a-f]{14}$")


def _money(value: object) -> Decimal:
    if value in {None, ""}:
        return Decimal("0")
    try:
        return Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"Invalid permit value in database: {value}") from exc


def _json_strings(value: str) -> list[str]:
    try:
        decoded = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(decoded, list):
        return []
    return [str(item) for item in decoded]


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = value.strip()
        key = cleaned.casefold()
        if cleaned and key not in seen:
            seen.add(key)
            result.append(cleaned)
    return sorted(result, key=str.casefold)


def _load_projects(database_path: Path) -> list[dict[str, Any]]:
    database_path = Path(database_path)
    if not database_path.is_file():
        raise FileNotFoundError(f"Radar database not found: {database_path}")

    connection = sqlite3.connect(
        f"{database_path.resolve().as_uri()}?mode=ro",
        uri=True,
    )
    connection.row_factory = sqlite3.Row
    try:
        try:
            rows = connection.execute(
                """
                SELECT
                    projects.project_id,
                    projects.grouping_status,
                    projects.listed_permit_value_total,
                    projects.max_listed_permit_value,
                    permits.jurisdiction,
                    permits.permit_number,
                    permits.project_category,
                    permits.project_type,
                    permits.issued_date,
                    permits.estimated_cost,
                    permits.description,
                    permits.site_address,
                    permits.city,
                    permits.state,
                    permits.postal_code,
                    permits.township,
                    permits.zoning_json,
                    permits.owner_business,
                    permits.general_contractor,
                    permits.parcel_numbers_json,
                    permits.source_url,
                    permits.source_period,
                    permits.source_pages_json,
                    permits.first_imported_at
                FROM projects
                JOIN project_permits USING (project_id)
                JOIN permits USING (record_id)
                WHERE permits.visibility = 'business_intelligence'
                ORDER BY
                    projects.project_id,
                    COALESCE(permits.issued_date, '') DESC,
                    permits.permit_number
                """
            ).fetchall()
        except sqlite3.OperationalError as exc:
            raise ValueError(
                "Database is not a Michiana Development Radar database"
            ) from exc
    finally:
        connection.close()

    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        project = grouped.setdefault(
            row["project_id"],
            {
                "project_id": row["project_id"],
                "grouping_status": row["grouping_status"],
                "listed_permit_value_total": row[
                    "listed_permit_value_total"
                ],
                "max_listed_permit_value": row["max_listed_permit_value"],
                "permits": [],
            },
        )
        project["permits"].append(
            {
                "jurisdiction": row["jurisdiction"],
                "permit_number": row["permit_number"],
                "project_category": row["project_category"],
                "project_type": row["project_type"],
                "issued_date": row["issued_date"],
                "estimated_cost": row["estimated_cost"],
                "description": row["description"],
                "site_address": row["site_address"],
                "city": row["city"],
                "state": row["state"],
                "postal_code": row["postal_code"],
                "township": row["township"],
                "zoning": _json_strings(row["zoning_json"]),
                "owner_business": row["owner_business"],
                "general_contractor": row["general_contractor"],
                "parcel_numbers": _json_strings(row["parcel_numbers_json"]),
                "first_imported_at": row["first_imported_at"],
                "source_url": row["source_url"],
                "source_period": row["source_period"],
                "source_pages": [
                    int(page)
                    for page in _json_strings(row["source_pages_json"])
                    if str(page).isdigit()
                ],
            }
        )

    projects: list[dict[str, Any]] = []
    for project in grouped.values():
        permits = project["permits"]
        permits.sort(
            key=lambda permit: (
                permit["issued_date"] or "",
                permit["permit_number"],
            ),
            reverse=True,
        )
        primary = max(
            permits,
            key=lambda permit: (
                _money(permit["estimated_cost"]),
                permit["issued_date"] or "",
                permit["permit_number"],
            ),
        )
        latest_dates = [
            permit["issued_date"]
            for permit in permits
            if permit["issued_date"]
        ]
        imported_dates = [
            permit["first_imported_at"]
            for permit in permits
            if permit["first_imported_at"]
        ]

        def first_value(field: str) -> str:
            value = primary.get(field)
            if value:
                return str(value)
            return next(
                (
                    str(permit[field])
                    for permit in permits
                    if permit.get(field)
                ),
                "",
            )

        project.update(
            {
                "permit_count": len(permits),
                "permit_numbers": [
                    permit["permit_number"] for permit in permits
                ],
                "latest_issued_date": max(latest_dates, default=None),
                "first_imported_at": min(imported_dates, default=None),
                "project_type": first_value("project_type"),
                "description": first_value("description"),
                "jurisdiction": first_value("jurisdiction"),
                "site_address": first_value("site_address"),
                "city": first_value("city"),
                "state": first_value("state"),
                "postal_code": first_value("postal_code"),
                "township": first_value("township"),
                "contractors": _unique(
                    [
                        str(permit["general_contractor"])
                        for permit in permits
                        if permit["general_contractor"]
                    ]
                ),
                "owner_businesses": _unique(
                    [
                        str(permit["owner_business"])
                        for permit in permits
                        if permit["owner_business"]
                    ]
                ),
                "project_types": _unique(
                    [
                        str(permit["project_type"])
                        for permit in permits
                        if permit["project_type"]
                    ]
                ),
            }
        )
        projects.append(project)

    return projects


def _search_text(project: dict[str, Any]) -> str:
    values: list[str] = [
        project["project_id"],
        project["project_type"],
        project["description"],
        project["site_address"],
        project["city"],
        project["township"],
        *project["permit_numbers"],
        *project["contractors"],
        *project["owner_businesses"],
    ]
    for permit in project["permits"]:
        values.extend(
            [
                permit["description"],
                permit["site_address"],
                permit["source_period"] or "",
                *permit["parcel_numbers"],
            ]
        )
    return " ".join(str(value) for value in values).casefold()


def _optional_money(value: str | Decimal | None, name: str) -> Decimal | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"{name} must be a number") from exc
    if result < 0:
        raise ValueError(f"{name} cannot be negative")
    return result


def query_project_feed(
    database_path: Path,
    *,
    search: str = "",
    jurisdiction: str = "",
    added_within_days: int | None = None,
    city: str = "",
    project_type: str = "",
    contractor: str = "",
    min_value: str | Decimal | None = None,
    max_value: str | Decimal | None = None,
    sort: str = "newest",
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    if sort not in VALID_SORTS:
        raise ValueError(
            f"sort must be one of: {', '.join(sorted(VALID_SORTS))}"
        )
    if limit < 1 or limit > 200:
        raise ValueError("limit must be between 1 and 200")
    if offset < 0:
        raise ValueError("offset cannot be negative")
    if added_within_days is not None:
        if added_within_days < 1 or added_within_days > 365:
            raise ValueError("added_within_days must be between 1 and 365")

    minimum = _optional_money(min_value, "min_value")
    maximum = _optional_money(max_value, "max_value")
    if minimum is not None and maximum is not None and minimum > maximum:
        raise ValueError("min_value cannot exceed max_value")

    all_projects = _load_projects(Path(database_path))
    normalized_search = search.strip().casefold()
    normalized_jurisdiction = jurisdiction.strip().casefold()
    normalized_city = city.strip().casefold()
    added_cutoff = (
        datetime.now(timezone.utc) - timedelta(days=added_within_days)
        if added_within_days is not None
        else None
    )
    normalized_type = project_type.strip().casefold()
    normalized_contractor = contractor.strip().casefold()

    filtered: list[dict[str, Any]] = []
    for project in all_projects:
        listed_value = _money(project["listed_permit_value_total"])
        if normalized_search and normalized_search not in _search_text(project):
            continue
        if (
            normalized_jurisdiction
            and project["jurisdiction"].casefold() != normalized_jurisdiction
        ):
            continue
        if added_cutoff is not None:
            first_imported_at = project.get("first_imported_at")
            if not first_imported_at:
                continue

            imported_at = datetime.fromisoformat(first_imported_at)
            if imported_at < added_cutoff:
                continue
        if normalized_city and project["city"].casefold() != normalized_city:
            continue
        if normalized_type and normalized_type not in {
            value.casefold() for value in project["project_types"]
        }:
            continue
        if normalized_contractor and normalized_contractor not in {
            value.casefold() for value in project["contractors"]
        }:
            continue
        if minimum is not None and listed_value < minimum:
            continue
        if maximum is not None and listed_value > maximum:
            continue
        filtered.append(project)

    top_opportunities = sorted(
        filtered,
        key=lambda project: (
            _money(project["listed_permit_value_total"]),
            project["latest_issued_date"] or "",
            project["project_id"],
        ),
        reverse=True,
    )[:5]

    if sort == "newest":
        filtered.sort(
            key=lambda project: (
                project["latest_issued_date"] or "",
                _money(project["listed_permit_value_total"]),
                project["project_id"],
            ),
            reverse=True,
        )
    elif sort == "oldest":
        filtered.sort(
            key=lambda project: (
                project["latest_issued_date"] or "9999-12-31",
                project["project_id"],
            )
        )
    elif sort == "discovered_desc":
        filtered.sort(
            key=lambda project: (
                project["first_imported_at"] or "",
                _money(project["listed_permit_value_total"]),
                project["project_id"],
            ),
            reverse=True,
        )
    elif sort == "value_desc":
        filtered.sort(
            key=lambda project: (
                _money(project["listed_permit_value_total"]),
                project["latest_issued_date"] or "",
                project["project_id"],
            ),
            reverse=True,
        )
    else:
        filtered.sort(
            key=lambda project: (
                _money(project["listed_permit_value_total"]),
                project["latest_issued_date"] or "",
                project["project_id"],
            )
        )

    result_count = len(filtered)
    filtered_value_total = sum(
        (
            _money(project["listed_permit_value_total"])
            for project in filtered
        ),
        Decimal("0"),
    )
    page = filtered[offset : offset + limit]
    all_permits = [
        permit
        for project in all_projects
        for permit in project["permits"]
    ]
    dates = [
        permit["issued_date"]
        for permit in all_permits
        if permit["issued_date"]
    ]
    total_value = sum(
        (
            _money(project["listed_permit_value_total"])
            for project in all_projects
        ),
        Decimal("0"),
    )

    return {
        "summary": {
            "project_count": len(all_projects),
            "permit_count": len(all_permits),
            "listed_value_total": str(total_value),
            "latest_issued_date": max(dates, default=None),
        },
        "facets": {
            "jurisdictions": _unique(
                [project["jurisdiction"] for project in all_projects]
            ),
            "cities": _unique(
                [project["city"] for project in all_projects]
            ),
            "project_types": _unique(
                [
                    project_type_name
                    for project in all_projects
                    for project_type_name in project["project_types"]
                ]
            ),
            "contractors": _unique(
                [
                    contractor_name
                    for project in all_projects
                    for contractor_name in project["contractors"]
                ]
            ),
        },
        "result_count": result_count,
        "returned_count": len(page),
        "filtered_summary": {
            "project_count": result_count,
            "listed_value_total": str(filtered_value_total),
        },
        "top_opportunities": top_opportunities,
        "limit": limit,
        "offset": offset,
        "projects": page,
    }


def get_project(database_path: Path, project_id: str) -> dict[str, Any]:
    if PROJECT_ID_RE.fullmatch(project_id) is None:
        raise ValueError("Invalid project ID")

    for project in _load_projects(Path(database_path)):
        if project["project_id"] == project_id:
            return project

    raise KeyError(f"Project not found: {project_id}")
