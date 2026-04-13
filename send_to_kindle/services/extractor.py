from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup
import trafilatura

from send_to_kindle.models import ArticleContent


class ExtractionError(Exception):
    pass


@dataclass(slots=True)
class Metadata:
    title: Optional[str]
    author: Optional[str]
    site_name: Optional[str]
    published_at: Optional[str]
    lead_image_url: Optional[str]


META_NAMES = {
    "author": ["author", "article:author", "parsely-author"],
    "site_name": ["og:site_name", "application-name"],
    "published_at": ["article:published_time", "pubdate", "parsely-pub-date", "date"],
    "lead_image": ["og:image", "twitter:image", "twitter:image:src"],
}


def extract_article(html: str, source_url: str) -> ArticleContent:
    cleaned_text = trafilatura.extract(
        html,
        include_comments=False,
        include_tables=False,
        favor_precision=True,
        no_fallback=False,
    )
    if not cleaned_text:
        raise ExtractionError("Could not extract a readable article body from the source URL")

    metadata = _extract_metadata(html, source_url)
    title = metadata.title or _fallback_title(cleaned_text)
    if not title:
        raise ExtractionError("Could not determine an article title")

    content_html = _text_to_html(cleaned_text)
    return ArticleContent(
        source_url=source_url,
        title=title,
        author=metadata.author,
        site_name=metadata.site_name,
        published_at=metadata.published_at,
        content_html=content_html,
        lead_image_url=metadata.lead_image_url,
    )


def _extract_metadata(html: str, source_url: str) -> Metadata:
    soup = BeautifulSoup(html, "html.parser")

    title = None
    page_heading = _find_heading_text(soup)
    if page_heading:
        title = page_heading
    if soup.title and soup.title.string:
        title = title or soup.title.string.strip()
    og_title = _find_meta_content(soup, ["og:title", "twitter:title"])
    if og_title and not title:
        title = og_title

    return Metadata(
        title=title,
        author=_find_meta_content(soup, META_NAMES["author"]),
        site_name=_find_meta_content(soup, META_NAMES["site_name"]),
        published_at=_find_meta_content(soup, META_NAMES["published_at"]),
        lead_image_url=_normalize_url(_find_meta_content(soup, META_NAMES["lead_image"]), source_url),
    )


def _find_meta_content(soup: BeautifulSoup, names: list[str]) -> Optional[str]:
    for name in names:
        tag = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
        if tag and tag.get("content"):
            content = tag["content"].strip()
            if content:
                return content
    return None


def _find_heading_text(soup: BeautifulSoup) -> Optional[str]:
    heading = soup.find("h1")
    if not heading:
        return None
    text = heading.get_text(" ", strip=True)
    return text or None


def _normalize_url(url: Optional[str], source_url: str) -> Optional[str]:
    if not url:
        return None
    return urljoin(source_url, url)


def _fallback_title(cleaned_text: str) -> Optional[str]:
    for line in cleaned_text.splitlines():
        candidate = line.strip()
        if candidate:
            return candidate[:120]
    return None


def _text_to_html(text: str) -> str:
    paragraphs = [segment.strip() for segment in text.splitlines() if segment.strip()]
    return "\n".join(f"<p>{escape(paragraph)}</p>" for paragraph in paragraphs)
