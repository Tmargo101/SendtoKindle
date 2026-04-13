from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import httpx

from send_to_kindle.config import Settings


class FetchError(Exception):
    def __init__(self, message: str, transient: bool):
        super().__init__(message)
        self.transient = transient


@dataclass(slots=True)
class FetchedPage:
    url: str
    html: str
    content_type: Optional[str]


async def fetch_url(url: str, settings: Settings) -> FetchedPage:
    headers = {"User-Agent": settings.user_agent}
    timeout = httpx.Timeout(settings.request_timeout_seconds)
    limits = httpx.Limits(max_connections=10, max_keepalive_connections=5)

    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, max_redirects=settings.max_redirects, limits=limits, headers=headers) as client:
            response = await client.get(url)
            response.raise_for_status()
    except httpx.TimeoutException as exc:
        raise FetchError("Timed out while fetching the source URL", transient=True) from exc
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code
        transient = status_code >= 500 or status_code in {408, 429}
        raise FetchError(f"Source URL returned HTTP {status_code}", transient=transient) from exc
    except httpx.HTTPError as exc:
        raise FetchError("Network error while fetching the source URL", transient=True) from exc

    content_type = response.headers.get("content-type", "")
    if "text/html" not in content_type:
        raise FetchError("Source URL did not return an HTML document", transient=False)

    return FetchedPage(url=str(response.url), html=response.text, content_type=content_type)


async def fetch_binary(url: str, settings: Settings) -> tuple[bytes, Optional[str]]:
    headers = {"User-Agent": settings.user_agent}
    timeout = httpx.Timeout(settings.request_timeout_seconds)
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, max_redirects=settings.max_redirects, headers=headers) as client:
            response = await client.get(url)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise FetchError("Unable to fetch lead image", transient=True) from exc

    content_type = response.headers.get("content-type")
    if not content_type or not content_type.startswith("image/"):
        raise FetchError("Lead image URL did not return an image", transient=False)

    return response.content, content_type
