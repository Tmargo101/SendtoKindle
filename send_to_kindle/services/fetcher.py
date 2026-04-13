from __future__ import annotations

import contextlib
import logging
from dataclasses import dataclass
from typing import Optional

import httpx

from send_to_kindle.config import Settings


logger = logging.getLogger(__name__)

HTTP_BROWSER_FALLBACK_STATUS_CODES = {401, 403, 429}
BLOCKED_PAGE_MARKERS = (
    "captcha",
    "cf-challenge",
    "challenge-platform",
    "enable javascript",
    "verify you are human",
    "access denied",
    "just a moment",
    "challenge",
)


class FetchError(Exception):
    def __init__(self, message: str, transient: bool, status_code: int | None = None):
        super().__init__(message)
        self.transient = transient
        self.status_code = status_code


@dataclass(slots=True)
class FetchedPage:
    url: str
    html: str
    content_type: Optional[str]


async def fetch_url(url: str, settings: Settings) -> FetchedPage:
    timeout = httpx.Timeout(settings.request_timeout_seconds)
    limits = httpx.Limits(max_connections=10, max_keepalive_connections=5)

    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            max_redirects=settings.max_redirects,
            limits=limits,
            headers=_build_browser_headers(settings),
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
    except httpx.TimeoutException as exc:
        raise FetchError("Timed out while fetching the source URL", transient=True) from exc
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code
        transient = status_code >= 500 or status_code in {408, 429}
        raise FetchError(f"Source URL returned HTTP {status_code}", transient=transient, status_code=status_code) from exc
    except httpx.HTTPError as exc:
        raise FetchError("Network error while fetching the source URL", transient=True) from exc

    content_type = response.headers.get("content-type", "")
    if "text/html" not in content_type:
        raise FetchError("Source URL did not return an HTML document", transient=False)

    logger.info("source fetched via HTTP", extra={"source_url": url, "final_url": str(response.url)})
    return FetchedPage(url=str(response.url), html=response.text, content_type=content_type)


async def fetch_url_in_browser(url: str, settings: Settings) -> FetchedPage:
    browser = None
    playwright = None
    context = None
    page = None
    try:
        from playwright.async_api import Error as PlaywrightError
        from playwright.async_api import TimeoutError as PlaywrightTimeoutError
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise FetchError("Browser runtime unavailable", transient=True) from exc

    try:
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=settings.user_agent,
            locale="en-US",
            extra_http_headers=_build_browser_headers(settings),
        )
        page = await context.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=int(settings.browser_fetch_timeout_seconds * 1000))
        await page.wait_for_timeout(1500)

        final_url = page.url
        html = await page.content()
        logger.info("source fetched via browser fallback", extra={"source_url": url, "final_url": final_url})
        return FetchedPage(url=final_url, html=html, content_type="text/html; charset=utf-8")
    except PlaywrightTimeoutError as exc:
        raise FetchError("Browser fallback timed out", transient=True) from exc
    except PlaywrightError as exc:
        raise FetchError("Browser fallback failed", transient=True) from exc
    except Exception as exc:
        raise FetchError("Browser fallback failed", transient=True) from exc
    finally:
        if page is not None:
            with contextlib.suppress(Exception):
                await page.close()
        if context is not None:
            with contextlib.suppress(Exception):
                await context.close()
        if browser is not None:
            with contextlib.suppress(Exception):
                await browser.close()
        if playwright is not None:
            with contextlib.suppress(Exception):
                await playwright.stop()


def should_retry_in_browser(
    settings: Settings,
    status_code: int | None = None,
    page: FetchedPage | None = None,
) -> bool:
    if not settings.browser_fetch_enabled:
        return False
    if status_code in HTTP_BROWSER_FALLBACK_STATUS_CODES:
        return True
    return page is not None and looks_like_blocked_or_interstitial_page(page.html)


def looks_like_blocked_or_interstitial_page(html: str) -> bool:
    html_lower = html.lower()
    return any(marker in html_lower for marker in BLOCKED_PAGE_MARKERS)


def _build_browser_headers(settings: Settings) -> dict[str, str]:
    return {
        "User-Agent": settings.user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Upgrade-Insecure-Requests": "1",
    }


async def fetch_binary(url: str, settings: Settings) -> tuple[bytes, Optional[str]]:
    timeout = httpx.Timeout(settings.request_timeout_seconds)
    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            max_redirects=settings.max_redirects,
            headers=_build_browser_headers(settings),
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise FetchError("Unable to fetch lead image", transient=True) from exc

    content_type = response.headers.get("content-type")
    if not content_type or not content_type.startswith("image/"):
        raise FetchError("Lead image URL did not return an image", transient=False)

    return response.content, content_type
