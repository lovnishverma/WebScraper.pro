"""
Core scraping engine.
Handles static (Requests + BS4) and dynamic (Playwright) scraping.
Implements UA rotation, retry logic, robots.txt checking, pagination, and infinite scroll.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import time
import urllib.robotparser
from dataclasses import dataclass, field
from typing import Any, Generator, Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class ScrapeRequest:
    """Fully-typed request configuration for the scraping engine."""

    url: str
    html_tag: Optional[str] = None
    css_selector: Optional[str] = None
    xpath_selector: Optional[str] = None
    attribute_name: Optional[str] = None
    extraction_type: str = "text"  # text | images | links | attributes | table | json_ld | full_html
    scrape_type: str = "static"  # static | dynamic
    follow_pagination: bool = False
    max_pages: int = 1
    infinite_scroll: bool = False
    scroll_count: int = 3
    download_images: bool = False
    custom_headers: dict = field(default_factory=dict)
    user_agent: Optional[str] = None
    delay_seconds: float = 1.0
    timeout_seconds: int = 30
    max_retries: int = 3
    check_robots_txt: bool = True
    deduplicate: bool = True


@dataclass
class ScrapedItem:
    """A single scraped datum."""

    content: str
    content_type: str
    page_url: str
    page_num: int
    item_index: int
    content_hash: str
    metadata: dict = field(default_factory=dict)


@dataclass
class ScrapeResponse:
    """Final response from the scraping engine."""

    items: list[ScrapedItem]
    pages_scraped: int
    error_count: int
    errors: list[str]
    duration_seconds: float


# ---------------------------------------------------------------------------
# User-Agent rotation
# ---------------------------------------------------------------------------

_ua_instance: Optional[UserAgent] = None


def _get_user_agent(preferred: Optional[str] = None) -> str:
    global _ua_instance
    if preferred:
        return preferred
    try:
        if _ua_instance is None:
            _ua_instance = UserAgent(fallback="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        return _ua_instance.random
    except Exception:
        return "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


# ---------------------------------------------------------------------------
# robots.txt checker
# ---------------------------------------------------------------------------


def _is_allowed_by_robots(url: str, user_agent: str = "*") -> bool:
    """Check whether a URL is allowed by the target site's robots.txt."""
    try:
        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        rp = urllib.robotparser.RobotFileParser()
        rp.set_url(robots_url)
        rp.read()
        return rp.can_fetch(user_agent, url)
    except Exception as exc:
        logger.warning("robots.txt check failed for %s: %s", url, exc)
        return True  # Allow on error — be conservative


# ---------------------------------------------------------------------------
# Content hashing for deduplication
# ---------------------------------------------------------------------------


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8", errors="replace")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# HTML Parsers
# ---------------------------------------------------------------------------


def _parse_html(html: str) -> BeautifulSoup:
    try:
        return BeautifulSoup(html, "lxml")
    except Exception:
        return BeautifulSoup(html, "html.parser")


def _extract_with_css(soup: BeautifulSoup, selector: str) -> list[Any]:
    return soup.select(selector)


def _extract_with_xpath(html: str, xpath: str) -> list[str]:
    """XPath extraction via lxml."""
    try:
        from lxml import etree

        tree = etree.fromstring(html.encode(), parser=etree.HTMLParser())
        results = tree.xpath(xpath)
        texts = []
        for r in results:
            if isinstance(r, str):
                texts.append(r.strip())
            elif hasattr(r, "text_content"):
                texts.append(r.text_content().strip())
            elif hasattr(r, "text"):
                texts.append((r.text or "").strip())
        return [t for t in texts if t]
    except Exception as exc:
        logger.warning("XPath extraction failed: %s", exc)
        return []


def _extract_json_ld(soup: BeautifulSoup) -> list[dict]:
    results = []
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
            results.append(data)
        except (json.JSONDecodeError, TypeError):
            pass
    return results


def _extract_tables(soup: BeautifulSoup) -> list[list[list[str]]]:
    tables = []
    for table in soup.find_all("table"):
        rows = []
        for tr in table.find_all("tr"):
            cells = [td.get_text(strip=True) for td in tr.find_all(["th", "td"])]
            if cells:
                rows.append(cells)
        if rows:
            tables.append(rows)
    return tables


# ---------------------------------------------------------------------------
# Content extractors
# ---------------------------------------------------------------------------


def _extract_items(
    soup: BeautifulSoup,
    raw_html: str,
    req: ScrapeRequest,
    page_url: str,
    page_num: int,
) -> list[ScrapedItem]:
    """Route extraction to the appropriate extractor."""
    items: list[ScrapedItem] = []

    if req.extraction_type == "json_ld":
        for idx, data in enumerate(_extract_json_ld(soup)):
            content = json.dumps(data, ensure_ascii=False)
            items.append(
                ScrapedItem(
                    content=content,
                    content_type="json_ld",
                    page_url=page_url,
                    page_num=page_num,
                    item_index=idx,
                    content_hash=_content_hash(content),
                )
            )
        return items

    if req.extraction_type == "table":
        for t_idx, table in enumerate(_extract_tables(soup)):
            content = json.dumps(table, ensure_ascii=False)
            items.append(
                ScrapedItem(
                    content=content,
                    content_type="table",
                    page_url=page_url,
                    page_num=page_num,
                    item_index=t_idx,
                    content_hash=_content_hash(content),
                )
            )
        return items

    if req.extraction_type == "full_html":
        content = str(soup)
        items.append(
            ScrapedItem(
                content=content,
                content_type="html",
                page_url=page_url,
                page_num=page_num,
                item_index=0,
                content_hash=_content_hash(content),
            )
        )
        return items

    # --- Resolve elements via CSS or XPath or Tag ---
    elements = []

    if req.xpath_selector:
        texts = _extract_with_xpath(raw_html, req.xpath_selector)
        for idx, text in enumerate(texts):
            items.append(
                ScrapedItem(
                    content=text,
                    content_type="text",
                    page_url=page_url,
                    page_num=page_num,
                    item_index=idx,
                    content_hash=_content_hash(text),
                )
            )
        return items

    if req.css_selector:
        elements = _extract_with_css(soup, req.css_selector)
    elif req.html_tag:
        elements = soup.find_all(req.html_tag)
    else:
        elements = soup.find_all(True)  # All elements

    for idx, el in enumerate(elements):
        if req.extraction_type == "text":
            content = el.get_text(separator=" ", strip=True)
        elif req.extraction_type == "links":
            href = el.get("href", "") if el.name == "a" else ""
            if not href:
                link_el = el.find("a")
                href = link_el.get("href", "") if link_el else ""
            if href:
                content = urljoin(page_url, href)
            else:
                continue
        elif req.extraction_type == "images":
            src = el.get("src", "") if el.name == "img" else ""
            if not src:
                img_el = el.find("img")
                src = img_el.get("src", "") if img_el else ""
            if src:
                content = urljoin(page_url, src)
            else:
                continue
        elif req.extraction_type == "attributes":
            if req.attribute_name:
                content = el.get(req.attribute_name, "")
            else:
                content = json.dumps(dict(el.attrs), ensure_ascii=False)
        else:
            content = el.get_text(separator=" ", strip=True)

        content = content.strip()
        if not content:
            continue

        items.append(
            ScrapedItem(
                content=content,
                content_type=req.extraction_type,
                page_url=page_url,
                page_num=page_num,
                item_index=idx,
                content_hash=_content_hash(content),
            )
        )

    return items


# ---------------------------------------------------------------------------
# Static scraper (Requests + BeautifulSoup)
# ---------------------------------------------------------------------------


class StaticScraper:
    """HTTP scraper using Requests with retry, UA rotation, and timeout handling."""

    def __init__(self, req: ScrapeRequest) -> None:
        self.req = req
        self.session = requests.Session()
        self._configure_session()

    def _configure_session(self) -> None:
        ua = _get_user_agent(self.req.user_agent)
        self.session.headers.update(
            {
                "User-Agent": ua,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
            }
        )
        if self.req.custom_headers:
            self.session.headers.update(self.req.custom_headers)

    @retry(
        retry=retry_if_exception_type((requests.ConnectionError, requests.Timeout)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    def _fetch(self, url: str) -> requests.Response:
        response = self.session.get(url, timeout=self.req.timeout_seconds, allow_redirects=True)
        response.raise_for_status()
        return response

    def scrape(self) -> Generator[tuple[str, str, int], None, None]:
        """Yields (html, page_url, page_num) for each page."""
        url = self.req.url
        page_num = 1

        while url and page_num <= self.req.max_pages:
            try:
                # Rotate UA per request
                self.session.headers["User-Agent"] = _get_user_agent(self.req.user_agent)
                response = self._fetch(url)
                html = response.text
                yield html, response.url, page_num

                if not self.req.follow_pagination or page_num >= self.req.max_pages:
                    break

                # Find next page link
                soup = _parse_html(html)
                next_url = _find_next_page(soup, response.url)
                if not next_url or next_url == url:
                    break

                url = next_url
                page_num += 1
                time.sleep(self.req.delay_seconds)

            except requests.HTTPError as exc:
                logger.error("HTTP error fetching %s: %s", url, exc)
                raise
            except Exception as exc:
                logger.error("Error fetching %s: %s", url, exc)
                raise

    def close(self) -> None:
        self.session.close()


def _find_next_page(soup: BeautifulSoup, current_url: str) -> Optional[str]:
    """Heuristic: find next pagination link."""
    patterns = [
        "a[rel='next']",
        "a.next",
        "a.pagination-next",
        "li.next a",
        "a[aria-label='Next']",
        ".next-page a",
        "#next a",
    ]
    for sel in patterns:
        el = soup.select_one(sel)
        if el and el.get("href"):
            return urljoin(current_url, el["href"])

    # Fallback: look for links with text "next"
    for a in soup.find_all("a", href=True):
        text = a.get_text(strip=True).lower()
        if text in ("next", "next »", "»", "›", "next page"):
            return urljoin(current_url, a["href"])

    return None


# ---------------------------------------------------------------------------
# Dynamic scraper (Playwright)
# ---------------------------------------------------------------------------


class DynamicScraper:
    """Playwright-based scraper for JS-rendered content with infinite scroll support."""

    def scrape(self, req: ScrapeRequest) -> Generator[tuple[str, str, int], None, None]:
        try:
            from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
        except ImportError:
            raise RuntimeError("Playwright not installed. Run: playwright install chromium")

        ua = _get_user_agent(req.user_agent)

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
            context = browser.new_context(
                user_agent=ua,
                viewport={"width": 1920, "height": 1080},
                extra_http_headers=req.custom_headers or {},
            )
            page = context.new_page()
            page.set_default_timeout(req.timeout_seconds * 1000)

            url = req.url
            page_num = 1

            while url and page_num <= req.max_pages:
                try:
                    page.goto(url, wait_until="networkidle", timeout=req.timeout_seconds * 1000)

                    if req.infinite_scroll:
                        _perform_infinite_scroll(page, req.scroll_count)

                    html = page.content()
                    final_url = page.url
                    yield html, final_url, page_num

                    if not req.follow_pagination or page_num >= req.max_pages:
                        break

                    # Try clicking next page button
                    next_url = _playwright_next_page(page, final_url)
                    if not next_url or next_url == url:
                        break

                    url = next_url
                    page_num += 1
                    time.sleep(req.delay_seconds)

                except PWTimeout as exc:
                    logger.error("Playwright timeout on %s: %s", url, exc)
                    raise
                except Exception as exc:
                    logger.error("Playwright error on %s: %s", url, exc)
                    raise

            context.close()
            browser.close()


def _perform_infinite_scroll(page, scroll_count: int) -> None:
    """Scroll to bottom repeatedly to trigger lazy loading."""
    for _ in range(scroll_count):
        prev_height = page.evaluate("document.body.scrollHeight")
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(1500)
        new_height = page.evaluate("document.body.scrollHeight")
        if new_height == prev_height:
            break


def _playwright_next_page(page, current_url: str) -> Optional[str]:
    """Try to find and return next page URL from Playwright page."""
    selectors = ["a[rel='next']", "a.next", "li.next a", "[aria-label='Next']"]
    for sel in selectors:
        try:
            el = page.query_selector(sel)
            if el:
                href = el.get_attribute("href")
                if href:
                    return urljoin(current_url, href)
        except Exception:
            pass
    return None


# ---------------------------------------------------------------------------
# Main engine entrypoint
# ---------------------------------------------------------------------------


def run_scrape(req: ScrapeRequest) -> ScrapeResponse:
    """
    Execute a scrape job and return structured results.
    Handles robots.txt, deduplication, pagination, and error accounting.
    """
    start_time = time.monotonic()
    items: list[ScrapedItem] = []
    errors: list[str] = []
    pages_scraped = 0
    seen_hashes: set[str] = set()

    # robots.txt
    if req.check_robots_txt:
        if not _is_allowed_by_robots(req.url):
            return ScrapeResponse(
                items=[],
                pages_scraped=0,
                error_count=1,
                errors=[f"robots.txt disallows scraping: {req.url}"],
                duration_seconds=time.monotonic() - start_time,
            )

    try:
        if req.scrape_type == "dynamic":
            scraper = DynamicScraper()
            pages = scraper.scrape(req)
        else:
            scraper = StaticScraper(req)
            pages = scraper.scrape()

        for html, page_url, page_num in pages:
            pages_scraped += 1
            soup = _parse_html(html)
            page_items = _extract_items(soup, html, req, page_url, page_num)

            for item in page_items:
                if req.deduplicate and item.content_hash in seen_hashes:
                    continue
                seen_hashes.add(item.content_hash)
                items.append(item)

        if req.scrape_type == "static" and hasattr(scraper, "close"):
            scraper.close()

    except Exception as exc:
        error_msg = f"Scrape failed: {type(exc).__name__}: {exc}"
        logger.exception(error_msg)
        errors.append(error_msg)

    return ScrapeResponse(
        items=items,
        pages_scraped=pages_scraped,
        error_count=len(errors),
        errors=errors,
        duration_seconds=time.monotonic() - start_time,
    )
