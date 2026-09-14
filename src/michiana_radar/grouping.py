from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Iterable

from .models import PermitRecord


@dataclass(frozen=True, slots=True)
class ProjectGroup:
    project_id: str
    permits: tuple[PermitRecord, ...]

    @property
    def listed_permit_value_total(self) -> Decimal:
        return sum(
            (permit.estimated_cost or Decimal("0") for permit in self.permits),
            Decimal("0"),
        )

    @property
    def max_listed_permit_value(self) -> Decimal:
        values = [
            permit.estimated_cost
            for permit in self.permits
            if permit.estimated_cost is not None
        ]
        return max(values, default=Decimal("0"))

    def to_dict(self) -> dict[str, object]:
        return {
            "project_id": self.project_id,
            "permit_numbers": [permit.permit_number for permit in self.permits],
            "listed_permit_value_total": str(self.listed_permit_value_total),
            "max_listed_permit_value": str(self.max_listed_permit_value),
            "grouping_status": (
                "probable_companion_permits" if len(self.permits) > 1 else "single_permit"
            ),
        }


def _normalized_address(permit: PermitRecord) -> str:
    value = f"{permit.site_address} {permit.city}".casefold()
    value = re.sub(r"\broad\b", "rd", value)
    value = re.sub(r"\bstreet\b", "st", value)
    value = re.sub(r"\bavenue\b", "ave", value)
    return re.sub(r"[^a-z0-9]+", "", value)


def _dates_within(left: date | None, right: date | None, days: int) -> bool:
    if left is None or right is None:
        return False
    return abs((left - right).days) <= days


def _explicitly_references(left: PermitRecord, right: PermitRecord) -> bool:
    left_description = left.description.casefold()
    right_description = right.description.casefold()
    return (
        left.permit_number.casefold() in right_description
        or right.permit_number.casefold() in left_description
    )


def permits_probably_share_project(left: PermitRecord, right: PermitRecord) -> bool:
    if left.jurisdiction != right.jurisdiction:
        return False
    if _explicitly_references(left, right):
        return True

    same_address = bool(
        left.site_address
        and right.site_address
        and _normalized_address(left) == _normalized_address(right)
    )
    shared_parcel = bool(set(left.parcel_numbers) & set(right.parcel_numbers))
    return (same_address or shared_parcel) and _dates_within(
        left.issued_date,
        right.issued_date,
        days=45,
    )


def _project_id(permits: list[PermitRecord]) -> str:
    identity = "|".join(
        [permits[0].jurisdiction, *sorted(permit.permit_number for permit in permits)]
    )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:14]
    return f"project-{digest}"


def group_permits(records: Iterable[PermitRecord]) -> list[ProjectGroup]:
    permits = list(records)
    parents = list(range(len(permits)))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parents[right_root] = left_root

    for left_index, left in enumerate(permits):
        for right_index in range(left_index + 1, len(permits)):
            if permits_probably_share_project(left, permits[right_index]):
                union(left_index, right_index)

    grouped: dict[int, list[PermitRecord]] = {}
    for index, permit in enumerate(permits):
        grouped.setdefault(find(index), []).append(permit)

    projects = [
        ProjectGroup(
            project_id=_project_id(group),
            permits=tuple(sorted(group, key=lambda permit: permit.permit_number)),
        )
        for group in grouped.values()
    ]
    return sorted(projects, key=lambda project: project.project_id)
