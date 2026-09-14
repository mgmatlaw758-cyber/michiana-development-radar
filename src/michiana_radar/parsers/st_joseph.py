from __future__ import annotations

import calendar
import re
import unicodedata
from decimal import Decimal, InvalidOperation
from typing import Iterable

from michiana_radar.models import PermitRecord, SourceRef
from michiana_radar.privacy import business_name_or_none, clean_whitespace

from .elkhart import Page

PERMIT_NUMBER_RE = re.compile(r"\bBD\d{8}\b", re.IGNORECASE)
CURRENCY_RE = re.compile(r"\$\s*(?P<amount>\d[\d,\s]*(?:\.[\d\s]{1,2})?)")
REPORT_DATE_RE = re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$")
PAGE_NUMBER_RE = re.compile(r"^\d{1,3}$")
REPORT_PERIOD_RE = re.compile(
    r"^FOR\s+THE\s+MONTH\s+OF\s+(?P<month>[A-Z]+),?\s+(?P<year>\d{4})$",
    re.IGNORECASE,
)
DETAIL_RE = re.compile(
    r"^(?P<prefix>.+?),\s*zoned\s+(?P<zoning>[^;]+?)\s*;\s*"
    r"Contractor\s*:\s*(?P<contractor>.+)$",
    re.IGNORECASE,
)

RAW_PERMIT_TYPE = "City-County Commercial Report"
JURISDICTION = "St. Joseph County"
MONTH_NUMBERS = {
    month.casefold(): number
    for number, month in enumerate(calendar.month_name)
    if month
}


def report_period_from_pages(pages: Iterable[Page]) -> str | None:
    for page in pages:
        normalized = unicodedata.normalize("NFKC", page.text)
        for raw_line in normalized.splitlines():
            line = clean_whitespace(raw_line)
            match = REPORT_PERIOD_RE.fullmatch(line)
            if match is None:
                continue
            month = MONTH_NUMBERS.get(match.group("month").casefold())
            if month is None:
                continue
            return f"{int(match.group('year')):04d}-{month:02d}"
    return None


def _lines(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", text)
    lines: list[str] = []
    for raw_line in normalized.splitlines():
        line = clean_whitespace(raw_line)
        if not line:
            continue
        if line.casefold() == "commercial report":
            continue
        if REPORT_DATE_RE.fullmatch(line):
            continue
        if PAGE_NUMBER_RE.fullmatch(line):
            continue
        if REPORT_PERIOD_RE.fullmatch(line):
            continue
        lines.append(line)
    return lines


def _page_blocks(page: Page) -> list[tuple[str, str]]:
    text = " ".join(_lines(page.text))
    matches = list(PERMIT_NUMBER_RE.finditer(text))
    blocks: list[tuple[str, str]] = []

    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        permit_number = match.group(0).upper()
        body = clean_whitespace(text[match.end() : end]).strip(" ,;")
        if body:
            blocks.append((permit_number, body))

    return blocks


def _extract_cost(body: str) -> tuple[Decimal | None, str]:
    match = CURRENCY_RE.search(body)
    if match is None:
        return None, body

    raw_amount = re.sub(r"\s+", "", match.group("amount")).replace(",", "")
    try:
        amount = Decimal(raw_amount)
    except InvalidOperation:
        amount = None

    without_cost = clean_whitespace(body[: match.start()] + " " + body[match.end() :])
    return amount, without_cost.strip(" ,;")


def _parse_block(
    permit_number: str,
    body: str,
    *,
    page_number: int,
    source_url: str,
    source_period: str | None,
) -> PermitRecord | None:
    estimated_cost, body_without_cost = _extract_cost(body)
    details = DETAIL_RE.fullmatch(body_without_cost)
    if details is None:
        return None

    prefix_parts = [
        clean_whitespace(part).strip(" ;")
        for part in details.group("prefix").split(",")
    ]
    prefix_parts = [part for part in prefix_parts if part]
    if len(prefix_parts) < 6:
        return None

    owner = prefix_parts[0]
    site_address = prefix_parts[-2]
    township = prefix_parts[-1].title()
    description = clean_whitespace(", ".join(prefix_parts[3:-2])).strip(" .")
    if not description:
        description = "Commercial permit"

    zoning = clean_whitespace(details.group("zoning")).strip(" ,;")
    contractor = clean_whitespace(details.group("contractor")).strip(" ,;")

    return PermitRecord(
        jurisdiction=JURISDICTION,
        permit_number=permit_number,
        raw_permit_type=RAW_PERMIT_TYPE,
        project_category="Commercial",
        project_type=description,
        issued_date=None,
        estimated_cost=estimated_cost,
        description=description,
        site_address=site_address,
        city="",
        state="IN",
        postal_code="",
        township=township,
        zoning=(zoning,) if zoning else (),
        owner_business=business_name_or_none(owner),
        general_contractor=business_name_or_none(contractor),
        parcel_numbers=(),
        source=SourceRef(
            url=source_url,
            period=source_period,
            pages=(page_number,),
        ),
        visibility="business_intelligence",
    )


def parse_commercial_report_pages(
    pages: Iterable[Page],
    *,
    source_url: str,
    source_period: str | None = None,
) -> list[PermitRecord]:
    records: list[PermitRecord] = []

    for page in pages:
        for permit_number, body in _page_blocks(page):
            record = _parse_block(
                permit_number,
                body,
                page_number=page.number,
                source_url=source_url,
                source_period=source_period,
            )
            if record is not None:
                records.append(record)

    return records
