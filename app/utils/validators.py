"""
Input validation and sanitization utilities.
All user-supplied strings pass through here before entering business logic.
"""
from __future__ import annotations

import re
from typing import Any, Optional
from urllib.parse import urlparse

import bleach


# Allowed HTML tags for any rich-text fields (none for our use case)
ALLOWED_TAGS: list[str] = []
ALLOWED_ATTRS: dict = {}

# Valid CSS selector pattern (permissive but blocks script injection)
_CSS_UNSAFE_PATTERN = re.compile(r"[<>\"']|javascript:", re.IGNORECASE)
_XPATH_UNSAFE_PATTERN = re.compile(r"[<>]|javascript:", re.IGNORECASE)


def sanitize_string(value: Any, max_length: int = 500) -> str:
    """Strip HTML tags and trim whitespace."""
    if not value:
        return ""
    cleaned = bleach.clean(str(value), tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS, strip=True)
    return cleaned[:max_length].strip()


def validate_url(url: str) -> tuple[bool, str]:
    """Validate URL format. Returns (is_valid, error_message)."""
    if not url:
        return False, "URL is required."
    url = url.strip()
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False, "URL must use http or https."
        if not parsed.netloc:
            return False, "URL must include a valid domain."
        # Block localhost/private IPs (SSRF prevention)
        host = parsed.hostname or ""
        blocked = ["localhost", "127.0.0.1", "0.0.0.0", "::1"]
        if host in blocked or host.startswith("192.168.") or host.startswith("10."):
            return False, "Requests to internal addresses are not allowed."
    except Exception:
        return False, "Invalid URL format."
    return True, ""


def validate_css_selector(selector: Optional[str]) -> tuple[bool, str]:
    if not selector:
        return True, ""
    if _CSS_UNSAFE_PATTERN.search(selector):
        return False, "CSS selector contains unsafe characters."
    return True, ""


def validate_xpath(xpath: Optional[str]) -> tuple[bool, str]:
    if not xpath:
        return True, ""
    if _XPATH_UNSAFE_PATTERN.search(xpath):
        return False, "XPath contains unsafe characters."
    return True, ""


def validate_job_data(data: dict) -> tuple[bool, dict]:
    """
    Validate all fields for a scrape job.
    Returns (is_valid, error_dict).
    """
    errors: dict[str, str] = {}

    url = data.get("url", "")
    valid, msg = validate_url(url)
    if not valid:
        errors["url"] = msg

    css = data.get("css_selector")
    valid, msg = validate_css_selector(css)
    if not valid:
        errors["css_selector"] = msg

    xpath = data.get("xpath_selector")
    valid, msg = validate_xpath(xpath)
    if not valid:
        errors["xpath_selector"] = msg

    extraction_type = data.get("extraction_type", "text")
    valid_extractions = ("text", "images", "links", "attributes", "table", "json_ld", "full_html")
    if extraction_type not in valid_extractions:
        errors["extraction_type"] = f"Must be one of: {', '.join(valid_extractions)}"

    scrape_type = data.get("scrape_type", "static")
    if scrape_type not in ("static", "dynamic"):
        errors["scrape_type"] = "Must be 'static' or 'dynamic'."

    try:
        max_pages = int(data.get("max_pages", 1))
        if not 1 <= max_pages <= 200:
            errors["max_pages"] = "max_pages must be between 1 and 200."
    except (TypeError, ValueError):
        errors["max_pages"] = "max_pages must be an integer."

    try:
        delay = float(data.get("delay_seconds", 1.0))
        if not 0 <= delay <= 60:
            errors["delay_seconds"] = "delay_seconds must be between 0 and 60."
    except (TypeError, ValueError):
        errors["delay_seconds"] = "delay_seconds must be a number."

    return len(errors) == 0, errors
