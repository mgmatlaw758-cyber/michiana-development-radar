from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Iterable

from michiana_radar.models import PermitRecord, SourceRef
from michiana_radar.privacy import (
    business_name_or_none,
    clean_whitespace,
    is_contact_line,
    redact_contact_data,
)

HEADER_RE = re.compile(
    r"^(?P<trade>[A-Za-z /]+)\s+\((?P<class>[CR])\)\s*-\s*(?P<kind>.+)$",
    re.IGNORECASE,
)
PERMIT_NUMBER_RE = re.compile(
    r"\b[A-Z]{2,6}(?:-[A-Z])?-\d{3,4}-\d{4}\b",
    re.IGNORECASE,
)
CURRENCY_RE = re.compile(r"\$([\d,]+(?:\.\d{1,2})?)")
DATE_RE = re.compile(r"^(\d{2}/\d{2}/\d{4})$")
PARCEL_RE = re.compile(r"\b\d{2}-\d{2}-\d{2}-\d{3}-\d{3}\.\d{3}-\d{3}\b")
CITY_RE = re.compile(
    r"^(?P<city>.+?),\s*IN(?:DIANA)?\s*(?P<postal>\d{5})(?:-\d{4})?$",
    re.IGNORECASE,
)

CONTACT_ROLES = {
    "land owner",
    "applicant",
    "general contractor",
    "electrical contractor",
    "mechanical contractor",
    "plumbing contractor",
    "registered well driller",
    "septic installer",
}
DETAIL_PREFIXES = (
    "residential sq ft:",
    "accessory sq ft:",
    "comm/manuf sq ft:",
    "agricultural sq ft:",
    "non building sq ft:",
    "state release #:",
    "scope of release:",
    "bin #:",
    "number of stories:",
    "height:",
    "driveway:",
    "basement:",
    "type of construction:",
    "mechanical comments:",
    "electrical amps:",
    "plumbing comments:",
    "number of bedrooms:",
    "number of baths:",
    "setbacks:",
    "front:",
    "rear:",
    "side:",
    "lot area:",
    "dodge code:",
    "comments:",
)


@dataclass(frozen=True, slots=True)
class Page:
    number: int
    text: str


@dataclass(frozen=True, slots=True)
class PermitBlock:
    permit_number: str
    pages: tuple[Page, ...]


def _lines(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", text)
    return [clean_whitespace(line) for line in normalized.splitlines() if line.strip()]


def _header_index(lines: list[str]) -> int | None:
    for index, line in enumerate(lines):
        if HEADER_RE.fullmatch(line):
            return index
    return None


def _primary_permit_number(lines: list[str]) -> str | None:
    header_index = _header_index(lines)
    if header_index is None:
        return None
    for line in lines[header_index + 1 : header_index + 7]:
        match = PERMIT_NUMBER_RE.search(line)
        if match:
            return match.group(0).upper()
    return None


def merge_continuation_pages(pages: Iterable[Page]) -> list[PermitBlock]:
    blocks: list[PermitBlock] = []
    for page in pages:
        number = _primary_permit_number(_lines(page.text))
        if number is None:
            continue
        if blocks and blocks[-1].permit_number == number:
            previous = blocks[-1]
            blocks[-1] = PermitBlock(number, previous.pages + (page,))
        else:
            blocks.append(PermitBlock(number, (page,)))
    return blocks


def _find_line(lines: list[str], prefix: str, start: int = 0) -> int | None:
    prefix = prefix.casefold()
    for index in range(start, len(lines)):
        if lines[index].casefold().startswith(prefix):
            return index
    return None


def _value_after_label(lines: list[str], label: str, start: int = 0) -> str:
    index = _find_line(lines, label, start)
    if index is None:
        return ""
    _, _, inline_value = lines[index].partition(":")
    if inline_value.strip():
        return clean_whitespace(inline_value)
    if index + 1 < len(lines):
        return clean_whitespace(lines[index + 1])
    return ""


def _parse_cost(lines: list[str], header_index: int) -> Decimal | None:
    for line in lines[header_index + 1 : header_index + 8]:
        match = CURRENCY_RE.search(line)
        if not match:
            continue
        try:
            return Decimal(match.group(1).replace(",", ""))
        except InvalidOperation:
            return None
    return None


def _parse_date(lines: list[str], header_index: int):
    for line in lines[header_index + 1 :]:
        match = DATE_RE.fullmatch(line)
        if match:
            return datetime.strptime(match.group(1), "%m/%d/%Y").date()
        if line.casefold().startswith("site address:"):
            break
    return None


def _parse_description(lines: list[str], header_index: int) -> str:
    site_index = _find_line(lines, "site address:", header_index)
    if site_index is None:
        return ""
    date_index = None
    for index in range(header_index + 1, site_index):
        if DATE_RE.fullmatch(lines[index]):
            date_index = index
            break
    if date_index is None:
        return ""
    description = redact_contact_data(" ".join(lines[date_index + 1 : site_index]))
    description = description.strip(" .")
    return description.capitalize() if description.isupper() else description


def _parse_location(lines: list[str], header_index: int) -> tuple[str, str, str]:
    site_index = _find_line(lines, "site address:", header_index)
    parcel_index = _find_line(lines, "parcel number:", header_index)
    if site_index is None:
        return "", "", ""

    _, _, inline_address = lines[site_index].partition(":")
    address = clean_whitespace(inline_address)
    search_end = parcel_index if parcel_index is not None else min(site_index + 5, len(lines))
    city = ""
    postal = ""

    for line in lines[site_index + 1 : search_end]:
        match = CITY_RE.fullmatch(line)
        if match:
            city = clean_whitespace(match.group("city")).title()
            postal = match.group("postal")
            break
        if not address:
            address = line

    return redact_contact_data(address), city, postal


def _parse_parcels(lines: list[str], header_index: int) -> tuple[str, ...]:
    parcel_index = _find_line(lines, "parcel number:", header_index)
    subdivision_index = _find_line(lines, "subdivision:", header_index)
    if parcel_index is None:
        return ()
    end = subdivision_index if subdivision_index is not None else parcel_index + 8
    matches: list[str] = []
    for line in lines[parcel_index:end]:
        for match in PARCEL_RE.findall(line):
            if match not in matches:
                matches.append(match)
    return tuple(matches)


def _parse_zoning(lines: list[str], header_index: int) -> tuple[str, ...]:
    raw = _value_after_label(lines, "zoning:", header_index)
    values: list[str] = []
    for part in raw.split("||"):
        code = clean_whitespace(part.split("(", 1)[0])
        if code and code not in values:
            values.append(code)
    return tuple(values)


def _looks_like_address(line: str) -> bool:
    lower = line.casefold()
    return bool(
        re.match(r"^\d", line)
        or lower.startswith(("po box", "p.o. box"))
        or CITY_RE.fullmatch(line)
        or re.search(r",\s*[A-Z]{2}\s+\d{5}", line, re.IGNORECASE)
    )


def _party_candidates(lines: list[str], role: str) -> list[str]:
    candidates: list[str] = []
    target = role.casefold()

    for index, line in enumerate(lines):
        normalized_role = line.casefold()
        if normalized_role.startswith("contacts:"):
            normalized_role = normalized_role.partition(":")[2].strip()
        if normalized_role != target:
            continue

        name_parts: list[str] = []
        for candidate in lines[index + 1 :]:
            lower = candidate.casefold()
            if lower in CONTACT_ROLES or lower.startswith(DETAIL_PREFIXES):
                break
            if is_contact_line(candidate) or _looks_like_address(candidate):
                break
            if lower in {"husband & wife", "h&w", "(h&w)", "h & w"}:
                continue
            name_parts.append(candidate)
            if len(name_parts) == 3:
                break

        if name_parts:
            candidates.append(clean_whitespace(" ".join(name_parts)))

    return candidates


def _business_party(lines: list[str], role: str) -> str | None:
    for candidate in _party_candidates(lines, role):
        business = business_name_or_none(candidate)
        if business:
            return business
    return None


def _normalize_type(raw_type: str) -> tuple[str, str, str]:
    match = HEADER_RE.fullmatch(raw_type)
    if not match:
        return "Other", raw_type, "hidden"

    permit_class = match.group("class").upper()
    trade = clean_whitespace(match.group("trade")).title()
    kind = clean_whitespace(match.group("kind")).title()
    category = "Commercial" if permit_class == "C" else "Residential"
    visibility = "business_intelligence" if permit_class == "C" else "hidden"

    if trade == "Building":
        type_map = {
            "New": "New building",
            "Addition": "Addition",
            "Remodel": "Remodel",
            "Demolition": "Demolition",
        }
        project_type = type_map.get(kind, kind)
    else:
        project_type = f"{trade}: {kind}"

    return category, project_type, visibility


def _parse_block(
    block: PermitBlock,
    source_url: str,
    source_period: str | None,
) -> PermitRecord | None:
    lines: list[str] = []
    for page in block.pages:
        lines.extend(_lines(page.text))

    header_index = _header_index(lines)
    if header_index is None:
        return None

    raw_type = lines[header_index]
    category, project_type, visibility = _normalize_type(raw_type)
    site_address, city, postal = _parse_location(lines, header_index)

    return PermitRecord(
        jurisdiction="Elkhart County",
        permit_number=block.permit_number,
        raw_permit_type=raw_type,
        project_category=category,
        project_type=project_type,
        issued_date=_parse_date(lines, header_index),
        estimated_cost=_parse_cost(lines, header_index),
        description=_parse_description(lines, header_index),
        site_address=site_address,
        city=city,
        state="IN",
        postal_code=postal,
        township=_value_after_label(lines, "township:", header_index),
        zoning=_parse_zoning(lines, header_index),
        owner_business=_business_party(lines, "Land Owner"),
        general_contractor=_business_party(lines, "General Contractor"),
        parcel_numbers=_parse_parcels(lines, header_index),
        source=SourceRef(
            url=source_url,
            period=source_period,
            pages=tuple(page.number for page in block.pages),
        ),
        visibility=visibility,
    )


def parse_permit_pages(
    pages: Iterable[Page],
    *,
    source_url: str,
    source_period: str | None = None,
    commercial_buildings_only: bool = True,
) -> list[PermitRecord]:
    records: list[PermitRecord] = []

    for block in merge_continuation_pages(pages):
        record = _parse_block(block, source_url, source_period)
        if record is None:
            continue
        if commercial_buildings_only and not record.raw_permit_type.casefold().startswith(
            "building (c)"
        ):
            continue
        records.append(record)

    return records
