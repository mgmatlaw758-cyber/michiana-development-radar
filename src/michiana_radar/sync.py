from __future__ import annotations

import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen

from .pdf import extract_pdf_pages
from .parsers.elkhart import parse_permit_pages
from .storage import import_records

DEFAULT_SOURCE_PAGE_URL = (
    "https://www.elkhartcountyplanninganddevelopment.com/Building.html"
)
OFFICIAL_HOSTS = frozenset(
    {
        "elkhartcountyplanninganddevelopment.com",
        "www.elkhartcountyplanninganddevelopment.com",
    }
)
USER_AGENT = (
    "MichianaDevelopmentRadar/0.3 "
    "(https://github.com/mgmatlaw758-cyber/michiana-development-radar)"
)
MAX_HTML_BYTES = 2 * 1024 * 1024
MAX_PDF_BYTES = 150 * 1024 * 1024
DOWNLOAD_CHUNK_BYTES = 64 * 1024

MONTH_NUMBERS = {
    "january": 1,
    "jaunary": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}
MONTH_NAMES = {
    month_number: month_name.title()
    for month_name, month_number in MONTH_NUMBERS.items()
    if month_name != "jaunary"
}
EXPORT_TITLE_RE = re.compile(
    r"\bBuilding\s+Permits\s*-\s*"
    r"(?P<month>[A-Za-z]+)\s+(?P<year>\d{4})\b",
    re.IGNORECASE,
)

ProgressCallback = Callable[[str], None]


@dataclass(frozen=True, slots=True)
class PermitExport:
    year: int
    month: int
    month_name: str
    source_url: str

    @property
    def period(self) -> str:
        return f"{self.year:04d}-{self.month:02d}"

    @property
    def filename(self) -> str:
        return (
            f"{self.year:04d}-{self.month:02d}-"
            f"{self.month_name.casefold()}-permits.pdf"
        )


class _AnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text_parts: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if tag.casefold() != "a" or self._href is not None:
            return
        attributes = dict(attrs)
        href = attributes.get("href")
        if href:
            self._href = href
            self._text_parts = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() != "a" or self._href is None:
            return
        text = " ".join("".join(self._text_parts).split())
        self.links.append((self._href, text))
        self._href = None
        self._text_parts = []


def _validate_official_url(url: str, *, require_pdf: bool) -> None:
    parsed = urlsplit(url)
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError(f"Invalid source URL: {url}") from exc

    if (
        parsed.scheme.casefold() != "https"
        or parsed.hostname is None
        or parsed.hostname.casefold() not in OFFICIAL_HOSTS
        or parsed.username is not None
        or parsed.password is not None
        or port not in {None, 443}
    ):
        raise ValueError(f"Refusing non-official Elkhart County URL: {url}")

    if require_pdf and not parsed.path.casefold().endswith(".pdf"):
        raise ValueError(f"Refusing non-PDF permit export URL: {url}")


def discover_exports_from_html(
    html: str,
    *,
    year: int,
    source_page_url: str = DEFAULT_SOURCE_PAGE_URL,
) -> list[PermitExport]:
    _validate_official_url(source_page_url, require_pdf=False)
    parser = _AnchorParser()
    parser.feed(html)

    exports_by_month: dict[int, PermitExport] = {}
    for href, title in parser.links:
        match = EXPORT_TITLE_RE.search(title)
        if match is None or int(match.group("year")) != year:
            continue

        month = MONTH_NUMBERS.get(match.group("month").casefold())
        if month is None:
            continue

        source_url = urljoin(source_page_url, href)
        try:
            _validate_official_url(source_url, require_pdf=True)
        except ValueError:
            continue

        exports_by_month.setdefault(
            month,
            PermitExport(
                year=year,
                month=month,
                month_name=MONTH_NAMES[month],
                source_url=source_url,
            ),
        )

    return [exports_by_month[month] for month in sorted(exports_by_month)]


def _read_source_page(url: str, *, timeout_seconds: int = 30) -> str:
    _validate_official_url(url, require_pdf=False)
    request = Request(
        url,
        headers={
            "Accept": "text/html,application/xhtml+xml",
            "User-Agent": USER_AGENT,
        },
    )
    with urlopen(request, timeout=timeout_seconds) as response:
        body = response.read(MAX_HTML_BYTES + 1)
        if len(body) > MAX_HTML_BYTES:
            raise ValueError("Elkhart source page exceeded the download limit")
        charset = response.headers.get_content_charset() or "utf-8"
    return body.decode(charset, errors="replace")


def discover_elkhart_exports(
    year: int,
    *,
    source_page_url: str = DEFAULT_SOURCE_PAGE_URL,
) -> list[PermitExport]:
    if year < 2017 or year > 2100:
        raise ValueError("Elkhart permit exports are supported for 2017 through 2100")
    return discover_exports_from_html(
        _read_source_page(source_page_url),
        year=year,
        source_page_url=source_page_url,
    )


def _is_cached_pdf(path: Path) -> bool:
    try:
        with path.open("rb") as file:
            return file.read(5) == b"%PDF-"
    except OSError:
        return False


def download_export(
    export: PermitExport,
    target: Path,
    *,
    refresh: bool = False,
    timeout_seconds: int = 60,
) -> str:
    _validate_official_url(export.source_url, require_pdf=True)
    target = Path(target)

    if not refresh and _is_cached_pdf(target):
        return "cached"

    target.parent.mkdir(parents=True, exist_ok=True)
    request = Request(
        export.source_url,
        headers={
            "Accept": "application/pdf",
            "User-Agent": USER_AGENT,
        },
    )

    temporary_path: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="wb",
            prefix=f".{target.name}.",
            suffix=".part",
            dir=target.parent,
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            with urlopen(request, timeout=timeout_seconds) as response:
                first_chunk = response.read(DOWNLOAD_CHUNK_BYTES)
                if not first_chunk.startswith(b"%PDF-"):
                    raise ValueError(
                        f"County response was not a PDF: {export.source_url}"
                    )

                total_bytes = len(first_chunk)
                if total_bytes > MAX_PDF_BYTES:
                    raise ValueError("Permit PDF exceeded the download limit")
                temporary_file.write(first_chunk)

                while True:
                    chunk = response.read(DOWNLOAD_CHUNK_BYTES)
                    if not chunk:
                        break
                    total_bytes += len(chunk)
                    if total_bytes > MAX_PDF_BYTES:
                        raise ValueError("Permit PDF exceeded the download limit")
                    temporary_file.write(chunk)

        os.replace(temporary_path, target)
        temporary_path = None
        return "downloaded"
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def sync_elkhart_year(
    *,
    year: int,
    database_path: Path,
    cache_directory: Path,
    source_page_url: str = DEFAULT_SOURCE_PAGE_URL,
    refresh: bool = False,
    progress: ProgressCallback | None = None,
) -> dict[str, object]:
    exports = discover_elkhart_exports(
        year,
        source_page_url=source_page_url,
    )
    if not exports:
        raise RuntimeError(f"No Elkhart County permit exports found for {year}")

    database_path = Path(database_path)
    year_cache = Path(cache_directory) / str(year)
    report_results: list[dict[str, object]] = []
    successful_summaries = []

    for export in exports:
        target = year_cache / export.filename
        result: dict[str, object] = {
            "period": export.period,
            "source_url": export.source_url,
            "cached_file": str(target),
        }
        try:
            if progress is not None:
                progress(f"{export.period}: downloading or using cache")
            download_status = download_export(
                export,
                target,
                refresh=refresh,
            )

            if progress is not None:
                progress(f"{export.period}: parsing and importing")
            records = parse_permit_pages(
                extract_pdf_pages(target),
                source_url=export.source_url,
                source_period=export.period,
            )
            summary = import_records(
                database_path,
                records,
                jurisdiction="Elkhart County",
                source_url=export.source_url,
                source_period=export.period,
                input_file=target.name,
            )
            successful_summaries.append(summary)
            result.update(
                {
                    "status": "processed",
                    "download_status": download_status,
                    **summary.to_dict(),
                }
            )
            if progress is not None:
                progress(
                    f"{export.period}: {summary.input_permit_count} permits, "
                    f"{summary.inserted_count} inserted, "
                    f"{summary.updated_count} updated"
                )
        except Exception as exc:
            result.update(
                {
                    "status": "failed",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            if progress is not None:
                progress(f"{export.period}: failed: {exc}")

        report_results.append(result)

    processed_count = len(successful_summaries)
    last_summary = successful_summaries[-1] if successful_summaries else None
    return {
        "jurisdiction": "Elkhart County",
        "year": year,
        "source_page_url": source_page_url,
        "database": str(database_path),
        "cache_directory": str(year_cache),
        "discovered_report_count": len(exports),
        "processed_report_count": processed_count,
        "failed_report_count": len(exports) - processed_count,
        "totals": {
            "input_permit_count": sum(
                summary.input_permit_count
                for summary in successful_summaries
            ),
            "inserted_count": sum(
                summary.inserted_count
                for summary in successful_summaries
            ),
            "updated_count": sum(
                summary.updated_count
                for summary in successful_summaries
            ),
            "unchanged_count": sum(
                summary.unchanged_count
                for summary in successful_summaries
            ),
            "stored_permit_count": (
                last_summary.stored_permit_count
                if last_summary is not None
                else None
            ),
            "stored_project_count": (
                last_summary.stored_project_count
                if last_summary is not None
                else None
            ),
        },
        "reports": report_results,
    }
