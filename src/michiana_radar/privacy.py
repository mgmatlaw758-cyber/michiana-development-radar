from __future__ import annotations

import re

EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_RE = re.compile(
    r"(?<!\d)(?:\+?1[ .-]?)?(?:\(\d{3}\)|\d{3})[ .-]?\d{3}[ .-]?\d{4}"
    r"(?:\s*(?:x|ext\.?|extension)\s*\d+)?(?!\d)",
    re.IGNORECASE,
)
CONTACT_LABEL_RE = re.compile(
    r"^(?:business|mobile|home|fax|phone|email)\s*:",
    re.IGNORECASE,
)
BUSINESS_RE = re.compile(
    r"\b(?:"
    r"llc|l\.l\.c\.|inc|incorporated|corp|corporation|company|co\.|"
    r"construction|builders?|contracting|electric|plumbing|hvac|excavating|"
    r"services?|properties|development|manufacturing|hardware|enterprises?|"
    r"associates|partners|group|university|school|church|ministries|authority|"
    r"city|county|township"
    r")\b",
    re.IGNORECASE,
)


def clean_whitespace(value: str) -> str:
    return " ".join(value.replace("\u00a0", " ").split())


def redact_contact_data(value: str) -> str:
    value = EMAIL_RE.sub("[redacted]", value)
    value = PHONE_RE.sub("[redacted]", value)
    return clean_whitespace(value)


def is_contact_line(value: str) -> bool:
    return bool(
        CONTACT_LABEL_RE.search(value.strip())
        or EMAIL_RE.search(value)
        or PHONE_RE.search(value)
    )


def is_probable_business_entity(value: str) -> bool:
    value = clean_whitespace(value)
    if not value or value.casefold() in {"self", "owner", "homeowner", "unknown"}:
        return False
    return bool(BUSINESS_RE.search(value))


def business_name_or_none(value: str) -> str | None:
    value = redact_contact_data(value).strip(" ,;")
    return value if is_probable_business_entity(value) else None
