from __future__ import annotations

from michiana_radar.st_joseph_sync import (
    candidates_from_building_html,
    candidates_from_media_payload,
)


def test_discovers_commercial_pdf_from_media_payload() -> None:
    payload = [
        {
            "id": 1234,
            "date_gmt": "2026-08-31T12:00:00",
            "source_url": (
                "https://southbendin.gov/wp-content/uploads/2026/08/"
                "JULY-2026-CITY-COUNTY-COMMERCIAL.pdf"
            ),
            "title": {"rendered": "JULY 2026 CITY COUNTY COMMERCIAL"},
        },
        {
            "id": 9999,
            "source_url": "https://example.com/not-official-commercial.pdf",
            "title": {"rendered": "Commercial"},
        },
        {
            "id": 8888,
            "source_url": (
                "https://southbendin.gov/wp-content/uploads/2026/08/"
                "unrelated-document.pdf"
            ),
            "title": {"rendered": "Unrelated document"},
        },
    ]

    candidates = candidates_from_media_payload(payload)

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.media_id == 1234
    assert candidate.uploaded_at == "2026-08-31T12:00:00"
    assert candidate.filename == "1234-JULY-2026-CITY-COUNTY-COMMERCIAL.pdf"


def test_discovers_current_report_link_from_building_page() -> None:
    html = """
    <html><body>
      <a href="/wp-content/uploads/2026/08/JULY-2026-CITY-COUNTY-COMMERCIAL.pdf">
        Monthly City-County Commercial Report
      </a>
      <a href="/wp-content/uploads/2026/08/house-report.pdf">
        Monthly New House Report
      </a>
    </body></html>
    """

    candidates = candidates_from_building_html(html)

    assert len(candidates) == 1
    assert candidates[0].source_url == (
        "https://southbendin.gov/wp-content/uploads/2026/08/"
        "JULY-2026-CITY-COUNTY-COMMERCIAL.pdf"
    )
