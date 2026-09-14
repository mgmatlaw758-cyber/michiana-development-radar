from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.error import HTTPError
from urllib.parse import urlencode, urljoin, urlsplit
from urllib.request import Request, urlopen

from .parsers.st_joseph import parse_commercial_report_pages, report_period_from_pages
from .pdf import extract_pdf_pages
from .storage import import_records

DEFAULT_BUILDING_PAGE_URL = (
    "https://southbendin.gov/department/community-investment/building/"
)
DEFAULT_MEDIA_API_URL = "https://southbendin.gov/wp-json/wp/v2/media"
OFFICIAL_HOSTS = frozenset({"southbendin.gov", "www.southbendin.gov"})
USER_AGENT = (
    "MichianaDevelopmentRadar/0.4 "
    "(https://github.com/mgmatlaw758-cyber/michiana-development-radar)"
)
MAX_HTML_BYTES = 2 * 1024 * 1024
MAX_JSON_BYTES = 8 * 1024 * 1024
MAX_PDF_BYTES = 150 * 1024 * 1024
DOWNLOAD_CHUNK_BYTES = 64 * 1024
MAX_MEDIA_PAGES = 10

ProgressCallback = Callable[[str], None]


@dataclass(frozen=True, slots=True)
class CommercialReportCandidate:
    source_url: str
    media_id: int | None = None
    uploaded_at: str = ""

    @property
    def filename(self) -> str:
        basename = Path(urlsplit(self.source_url).path).name or "commercial-report.pdf"
        if self.media_id is None:
            return basename
        return f"{self.media_id}-{basename}"


class _CommercialReportLinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if tag.casefold() != "a" or self._href is not None:
            return
        href = dict(attrs).get("href")
        if href:
            self._href = href
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() != "a" or self._href is None:
            return
        self.links.append((self._href, " ".join("".join(self._text).split())))
        self._href = None
        self._text = []


def _validate_official_url(url: str, *, require_pdf: bool = False) -> None:
    parsed = urlsplit(url)
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError(f"Invalid South Bend source URL: {url}") from exc

    if (
        parsed.scheme.casefold() != "https"
        or parsed.hostname is None
        or parsed.hostname.casefold() not in OFFICIAL_HOSTS
        or parsed.username is not None
        or parsed.password is not None
        or port not in {None, 443}
    ):
        raise ValueError(f"Refusing non-official South Bend URL: {url}")

    if require_pdf and not parsed.path.casefold().endswith(".pdf"):
        raise ValueError(f"Refusing non-PDF commercial report URL: {url}")


def candidates_from_media_payload(payload: object) -> list[CommercialReportCandidate]:
    if not isinstance(payload, list):
        raise ValueError("South Bend media API returned an unexpected response")

    candidates: list[CommercialReportCandidate] = []
    seen_urls: set[str] = set()
    for item in payload:
        if not isinstance(item, dict):
            continue
        source_url = item.get("source_url")
        if not isinstance(source_url, str):
            continue
        try:
            _validate_official_url(source_url, require_pdf=True)
        except ValueError:
            continue

        title = item.get("title")
        rendered_title = ""
        if isinstance(title, dict) and isinstance(title.get("rendered"), str):
            rendered_title = title["rendered"]
        searchable = f"{rendered_title} {Path(urlsplit(source_url).path).name}".casefold()
        if "commercial" not in searchable:
            continue
        if source_url in seen_urls:
            continue

        media_id = item.get("id")
        if not isinstance(media_id, int):
            media_id = None
        uploaded_at = item.get("date_gmt") or item.get("date") or ""
        if not isinstance(uploaded_at, str):
            uploaded_at = ""
        candidates.append(
            CommercialReportCandidate(
                source_url=source_url,
                media_id=media_id,
                uploaded_at=uploaded_at,
            )
        )
        seen_urls.add(source_url)

    return candidates


def candidates_from_building_html(
    html: str,
    *,
    source_page_url: str = DEFAULT_BUILDING_PAGE_URL,
) -> list[CommercialReportCandidate]:
    _validate_official_url(source_page_url)
    parser = _CommercialReportLinkParser()
    parser.feed(html)

    candidates: list[CommercialReportCandidate] = []
    seen_urls: set[str] = set()
    for href, title in parser.links:
        if "commercial report" not in title.casefold():
            continue
        source_url = urljoin(source_page_url, href)
        try:
            _validate_official_url(source_url, require_pdf=True)
        except ValueError:
            continue
        if source_url in seen_urls:
            continue
        candidates.append(CommercialReportCandidate(source_url=source_url))
        seen_urls.add(source_url)
    return candidates


def _read_limited_text(url: str, *, accept: str, maximum_bytes: int) -> str:
    _validate_official_url(url)
    request = Request(url, headers={"Accept": accept, "User-Agent": USER_AGENT})
    with urlopen(request, timeout=30) as response:
        body = response.read(maximum_bytes + 1)
        if len(body) > maximum_bytes:
            raise ValueError(f"South Bend response exceeded {maximum_bytes} bytes")
        charset = response.headers.get_content_charset() or "utf-8"
    return body.decode(charset, errors="replace")


def _discover_media_candidates(
    year: int,
    *,
    media_api_url: str = DEFAULT_MEDIA_API_URL,
) -> list[CommercialReportCandidate]:
    _validate_official_url(media_api_url)
    discovered: list[CommercialReportCandidate] = []
    seen_urls: set[str] = set()

    for page in range(1, MAX_MEDIA_PAGES + 1):
        query = urlencode(
            {
                "search": "commercial",
                "per_page": 100,
                "page": page,
                "after": f"{year - 1:04d}-12-01T00:00:00",
                "before": f"{year + 1:04d}-03-01T00:00:00",
                "orderby": "date",
                "order": "asc",
            }
        )
        url = f"{media_api_url}?{query}"
        try:
            raw = _read_limited_text(
                url,
                accept="application/json",
                maximum_bytes=MAX_JSON_BYTES,
            )
        except HTTPError as exc:
            if page > 1 and exc.code in {400, 404}:
                break
            raise

        payload = json.loads(raw)
        page_candidates = candidates_from_media_payload(payload)
        for candidate in page_candidates:
            if candidate.source_url not in seen_urls:
                discovered.append(candidate)
                seen_urls.add(candidate.source_url)

        if not isinstance(payload, list) or len(payload) < 100:
            break

    return discovered


def _discover_current_candidate(
    *,
    source_page_url: str = DEFAULT_BUILDING_PAGE_URL,
) -> list[CommercialReportCandidate]:
    html = _read_limited_text(
        source_page_url,
        accept="text/html,application/xhtml+xml",
        maximum_bytes=MAX_HTML_BYTES,
    )
    return candidates_from_building_html(html, source_page_url=source_page_url)


def discover_st_joseph_candidates(
    year: int,
    *,
    media_api_url: str = DEFAULT_MEDIA_API_URL,
    source_page_url: str = DEFAULT_BUILDING_PAGE_URL,
) -> list[CommercialReportCandidate]:
    if year < 2017 or year > 2100:
        raise ValueError("St. Joseph commercial reports are supported for 2017 through 2100")

    candidates: list[CommercialReportCandidate] = []
    seen_urls: set[str] = set()
    media_error: Exception | None = None

    try:
        for candidate in _discover_media_candidates(year, media_api_url=media_api_url):
            if candidate.source_url not in seen_urls:
                candidates.append(candidate)
                seen_urls.add(candidate.source_url)
    except Exception as exc:
        media_error = exc

    try:
        current_candidates = _discover_current_candidate(source_page_url=source_page_url)
    except Exception:
        current_candidates = []

    for candidate in current_candidates:
        if candidate.source_url not in seen_urls:
            candidates.append(candidate)
            seen_urls.add(candidate.source_url)

    if not candidates and media_error is not None:
        raise RuntimeError(f"Could not discover South Bend commercial reports: {media_error}")
    if not candidates:
        raise RuntimeError("No South Bend commercial report candidates were found")

    return candidates


def _is_cached_pdf(path: Path) -> bool:
    try:
        with path.open("rb") as file:
            return file.read(5) == b"%PDF-"
    except OSError:
        return False


def download_report(
    candidate: CommercialReportCandidate,
    target: Path,
    *,
    refresh: bool = False,
    timeout_seconds: int = 60,
) -> str:
    _validate_official_url(candidate.source_url, require_pdf=True)
    target = Path(target)
    if not refresh and _is_cached_pdf(target):
        return "cached"

    target.parent.mkdir(parents=True, exist_ok=True)
    request = Request(
        candidate.source_url,
        headers={"Accept": "application/pdf", "User-Agent": USER_AGENT},
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
                total_bytes = 0
                while True:
                    chunk = response.read(DOWNLOAD_CHUNK_BYTES)
                    if not chunk:
                        break
                    if total_bytes == 0 and not chunk.startswith(b"%PDF-"):
                        raise ValueError(
                            f"South Bend response was not a PDF: {candidate.source_url}"
                        )
                    total_bytes += len(chunk)
                    if total_bytes > MAX_PDF_BYTES:
                        raise ValueError("Commercial report PDF exceeded the download limit")
                    temporary_file.write(chunk)

            if total_bytes == 0:
                raise ValueError(f"South Bend returned an empty PDF: {candidate.source_url}")

        os.replace(temporary_path, target)
        temporary_path = None
        return "downloaded"
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def sync_st_joseph_year(
    *,
    year: int,
    database_path: Path,
    cache_directory: Path,
    media_api_url: str = DEFAULT_MEDIA_API_URL,
    source_page_url: str = DEFAULT_BUILDING_PAGE_URL,
    refresh: bool = False,
    progress: ProgressCallback | None = None,
) -> dict[str, object]:
    candidates = discover_st_joseph_candidates(
        year,
        media_api_url=media_api_url,
        source_page_url=source_page_url,
    )
    database_path = Path(database_path)
    year_cache = Path(cache_directory) / str(year)
    inspection_results: list[dict[str, object]] = []
    selected_by_period: dict[str, tuple[CommercialReportCandidate, Path, str]] = {}

    for candidate in candidates:
        target = year_cache / candidate.filename
        result: dict[str, object] = {
            "source_url": candidate.source_url,
            "cached_file": str(target),
        }
        try:
            if progress is not None:
                progress(f"candidate: downloading or using cache: {candidate.source_url}")
            download_status = download_report(candidate, target, refresh=refresh)
            pages = extract_pdf_pages(target)
            period = report_period_from_pages(pages)
            result["download_status"] = download_status
            result["period"] = period

            if period is None:
                result["status"] = "skipped_not_commercial_report"
            elif not period.startswith(f"{year:04d}-"):
                result["status"] = "skipped_other_year"
            else:
                result["status"] = "candidate"
                rank = candidate.uploaded_at or f"id-{candidate.media_id or 0:012d}"
                previous = selected_by_period.get(period)
                if previous is None or rank >= previous[2]:
                    selected_by_period[period] = (candidate, target, rank)
        except Exception as exc:
            result.update(
                {
                    "status": "failed_inspection",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            if progress is not None:
                progress(f"candidate failed: {exc}")
        inspection_results.append(result)

    if not selected_by_period:
        raise RuntimeError(f"No St. Joseph commercial reports matched report year {year}")

    report_results: list[dict[str, object]] = []
    successful_summaries = []
    for period in sorted(selected_by_period):
        candidate, target, _ = selected_by_period[period]
        result: dict[str, object] = {
            "period": period,
            "source_url": candidate.source_url,
            "cached_file": str(target),
        }
        try:
            if progress is not None:
                progress(f"{period}: parsing and importing")
            pages = extract_pdf_pages(target)
            records = parse_commercial_report_pages(
                pages,
                source_url=candidate.source_url,
                source_period=period,
            )
            if not records:
                raise ValueError("commercial report contained no parseable permit records")
            summary = import_records(
                database_path,
                records,
                jurisdiction="St. Joseph County",
                source_url=candidate.source_url,
                source_period=period,
                input_file=target.name,
            )
            successful_summaries.append(summary)
            result.update({"status": "processed", **summary.to_dict()})
            if progress is not None:
                progress(
                    f"{period}: {summary.input_permit_count} permits, "
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
                progress(f"{period}: failed: {exc}")
        report_results.append(result)

    last_summary = successful_summaries[-1] if successful_summaries else None
    return {
        "jurisdiction": "St. Joseph County",
        "year": year,
        "source_page_url": source_page_url,
        "media_api_url": media_api_url,
        "database": str(database_path),
        "cache_directory": str(year_cache),
        "discovered_candidate_count": len(candidates),
        "matched_report_count": len(selected_by_period),
        "processed_report_count": len(successful_summaries),
        "failed_report_count": sum(
            1 for result in report_results if result.get("status") == "failed"
        ),
        "stored_permit_count": (
            last_summary.stored_permit_count if last_summary is not None else 0
        ),
        "stored_project_count": (
            last_summary.stored_project_count if last_summary is not None else 0
        ),
        "inspections": inspection_results,
        "reports": report_results,
    }
