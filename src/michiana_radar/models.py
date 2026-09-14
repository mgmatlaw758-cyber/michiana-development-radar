from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

Visibility = Literal["business_intelligence", "hidden"]


@dataclass(frozen=True, slots=True)
class SourceRef:
    url: str
    period: str | None
    pages: tuple[int, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "url": self.url,
            "period": self.period,
            "pages": list(self.pages),
        }


@dataclass(frozen=True, slots=True)
class PermitRecord:
    jurisdiction: str
    permit_number: str
    raw_permit_type: str
    project_category: str
    project_type: str
    issued_date: date | None
    estimated_cost: Decimal | None
    description: str
    site_address: str
    city: str
    state: str
    postal_code: str
    township: str
    zoning: tuple[str, ...]
    owner_business: str | None
    general_contractor: str | None
    parcel_numbers: tuple[str, ...]
    source: SourceRef
    visibility: Visibility

    @property
    def record_id(self) -> str:
        jurisdiction = self.jurisdiction.lower().replace(" ", "-")
        return f"{jurisdiction}-{self.permit_number.lower()}"

    def to_dict(self) -> dict[str, object]:
        return {
            "record_id": self.record_id,
            "jurisdiction": self.jurisdiction,
            "permit_number": self.permit_number,
            "raw_permit_type": self.raw_permit_type,
            "project_category": self.project_category,
            "project_type": self.project_type,
            "issued_date": self.issued_date.isoformat() if self.issued_date else None,
            "estimated_cost": (
                str(self.estimated_cost) if self.estimated_cost is not None else None
            ),
            "description": self.description,
            "site_address": self.site_address,
            "city": self.city,
            "state": self.state,
            "postal_code": self.postal_code,
            "township": self.township,
            "zoning": list(self.zoning),
            "owner_business": self.owner_business,
            "general_contractor": self.general_contractor,
            "parcel_numbers": list(self.parcel_numbers),
            "source": self.source.to_dict(),
            "visibility": self.visibility,
        }
