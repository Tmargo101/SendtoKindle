from __future__ import annotations

from dataclasses import dataclass
import re
import textwrap
from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup, NavigableString, Tag
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

ALLOWED_TAGS = {
    "a",
    "blockquote",
    "br",
    "code",
    "del",
    "em",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "i",
    "li",
    "ol",
    "p",
    "pre",
    "s",
    "small",
    "strike",
    "strong",
    "sub",
    "sup",
    "u",
    "ul",
}
ALLOWED_ATTRIBUTES = {
    "a": {"href"},
}
INLINE_TAGS = {
    "a",
    "code",
    "del",
    "em",
    "i",
    "small",
    "strike",
    "strong",
    "sub",
    "sup",
    "u",
}
SENTENCE_END_RE = re.compile(r"""[.!?…'"”)\]]$""")
STARTS_WITH_WORD_RE = re.compile(r"^[A-Za-z0-9\"'“‘(]")
ENDS_WITH_WORD_RE = re.compile(r"[A-Za-z0-9\"'”’)]$")


def extract_article(html: str, source_url: str) -> ArticleContent:
    cleaned_html = trafilatura.extract(
        html,
        include_comments=False,
        include_tables=False,
        include_formatting=True,
        include_links=True,
        favor_precision=True,
        no_fallback=False,
        output_format="html",
    )
    if not cleaned_html:
        raise ExtractionError("Could not extract a readable article body from the source URL")

    metadata = _extract_metadata(html, source_url)
    title = metadata.title or _fallback_title(cleaned_html)
    if not title:
        raise ExtractionError("Could not determine an article title")

    source_ordered_lists = _extract_source_ordered_lists(html)
    content_html = _sanitize_content_html(cleaned_html, title, source_ordered_lists)
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
    soup = BeautifulSoup(cleaned_text, "html.parser")
    for heading_name in ("h1", "h2", "h3"):
        heading = soup.find(heading_name)
        if heading:
            candidate = heading.get_text(" ", strip=True)
            if candidate:
                return candidate[:120]
    for line in soup.get_text("\n", strip=True).splitlines():
        candidate = line.strip()
        if candidate:
            return candidate[:120]
    return None


def _extract_source_ordered_lists(html: str) -> dict[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    source_lists: dict[str, str] = {}
    for heading in soup.find_all(["h2", "h3", "h4", "h5", "h6"]):
        heading_text = _normalize_text_signature(heading.get_text(" ", strip=True))
        if not heading_text:
            continue
        sibling = heading.find_next_sibling()
        while sibling is not None and isinstance(sibling, NavigableString):
            sibling = sibling.find_next_sibling()
        if isinstance(sibling, Tag) and sibling.name == "ol":
            source_lists[heading_text] = str(sibling)
    return source_lists


def _sanitize_content_html(content_html: str, title: str, source_ordered_lists: dict[str, str]) -> str:
    soup = BeautifulSoup(content_html, "html.parser")
    container = soup.body or soup
    _remove_duplicate_title_heading(container, title)
    _sanitize_node(container)
    _normalize_list_items(container)
    _restore_source_ordered_lists(container, source_ordered_lists)
    _normalize_preformatted_blocks(container)
    _merge_broken_paragraphs(container)
    _trim_inline_tag_whitespace(container)
    _normalize_inline_spacing(container)
    fragments = []
    for child in container.children:
        rendered = _render_node(child)
        if rendered:
            fragments.append(rendered)
    return _normalize_rendered_html("\n".join(fragments))


def _remove_duplicate_title_heading(container: Tag, title: str) -> None:
    normalized_title = " ".join(title.split()).casefold()
    for heading_name in ("h1", "h2"):
        heading = container.find(heading_name)
        if heading is None:
            continue
        heading_text = " ".join(heading.get_text(" ", strip=True).split()).casefold()
        if heading_text == normalized_title:
            heading.decompose()
        return


def _sanitize_node(node: Tag) -> None:
    for child in list(node.children):
        if isinstance(child, NavigableString):
            continue
        if not isinstance(child, Tag):
            child.extract()
            continue
        _sanitize_node(child)
        if child.name not in ALLOWED_TAGS:
            child.unwrap()
            continue
        allowed_attributes = ALLOWED_ATTRIBUTES.get(child.name, set())
        for attribute_name in list(child.attrs):
            if attribute_name not in allowed_attributes:
                del child.attrs[attribute_name]


def _normalize_list_items(container: Tag) -> None:
    for list_item in container.find_all("li"):
        for child in list(list_item.children):
            if not isinstance(child, Tag):
                continue
            if child.name == "p" and _can_unwrap_paragraph_in_list_item(list_item, child):
                _unwrap_preserving_spacing(child)
            elif child.name in INLINE_TAGS and not child.get_text("", strip=True) and not child.get("href"):
                child.decompose()


def _can_unwrap_paragraph_in_list_item(list_item: Tag, paragraph: Tag) -> bool:
    for sibling in list_item.children:
        if sibling is paragraph or isinstance(sibling, NavigableString):
            continue
        if not isinstance(sibling, Tag):
            return False
        if sibling.name not in INLINE_TAGS:
            return False
    return True


def _unwrap_preserving_spacing(tag: Tag) -> None:
    previous = tag.previous_sibling
    contents = list(tag.contents)
    tag.unwrap()
    if previous is not None and contents:
        first = contents[0]
        if isinstance(first, NavigableString) and not str(first).startswith(" "):
            first.replace_with(NavigableString(f" {str(first)}"))


def _restore_source_ordered_lists(container: Tag, source_ordered_lists: dict[str, str]) -> None:
    if not source_ordered_lists:
        return
    for candidate_list in container.find_all(["ul", "ol"]):
        heading_text = _previous_heading_text(candidate_list)
        if not heading_text:
            continue
        source_list_html = source_ordered_lists.get(heading_text)
        if not source_list_html:
            continue
        replacement_soup = BeautifulSoup(source_list_html, "html.parser")
        replacement_list = replacement_soup.find("ol")
        if replacement_list is None:
            continue
        _sanitize_node(replacement_list)
        _normalize_list_items(replacement_list)
        candidate_list.replace_with(replacement_list)


def _normalize_preformatted_blocks(container: Tag) -> None:
    for pre_block in container.find_all("pre"):
        text = pre_block.get_text("", strip=False).replace("\r\n", "\n").replace("\r", "\n")
        text = textwrap.dedent(text).strip()
        pre_block.clear()
        pre_block.append(NavigableString(text))


def _previous_heading_text(node: Tag) -> Optional[str]:
    for sibling in node.previous_siblings:
        if isinstance(sibling, NavigableString):
            continue
        if not isinstance(sibling, Tag):
            continue
        if sibling.name in {"h2", "h3", "h4", "h5", "h6"}:
            text = _normalize_text_signature(sibling.get_text(" ", strip=True))
            return text or None
    return None


def _merge_broken_paragraphs(container: Tag) -> None:
    paragraphs = [child for child in container.find_all("p", recursive=False)]
    index = 0
    while index < len(paragraphs) - 1:
        current = paragraphs[index]
        following = paragraphs[index + 1]
        if _should_merge_paragraphs(current, following):
            _append_paragraph_contents(current, following)
            following.decompose()
            paragraphs.pop(index + 1)
            continue
        index += 1


def _should_merge_paragraphs(current: Tag, following: Tag) -> bool:
    current_text = current.get_text(" ", strip=True)
    following_text = following.get_text(" ", strip=True)
    if not current_text or not following_text:
        return False
    if SENTENCE_END_RE.search(current_text):
        return False
    if not _has_only_inline_children(current) or not _has_only_inline_children(following):
        return False
    return True


def _has_only_inline_children(paragraph: Tag) -> bool:
    for child in paragraph.children:
        if isinstance(child, NavigableString):
            continue
        if not isinstance(child, Tag):
            return False
        if child.name not in INLINE_TAGS:
            return False
    return True


def _append_paragraph_contents(current: Tag, following: Tag) -> None:
    current.append(NavigableString(" "))
    for child in list(following.contents):
        current.append(child.extract())


def _trim_inline_tag_whitespace(node: Tag) -> None:
    for child in node.children:
        if isinstance(child, Tag):
            _trim_inline_tag_whitespace(child)

    if node.name not in INLINE_TAGS:
        return

    first_text = node.find(string=True)
    if first_text is not None:
        original = str(first_text)
        trimmed = original.lstrip()
        if trimmed != original:
            removed = original[: len(original) - len(trimmed)]
            first_text.replace_with(NavigableString(trimmed))
            node.insert_before(NavigableString(removed))

    last_text = next((descendant for descendant in reversed(list(node.descendants)) if isinstance(descendant, NavigableString)), None)
    if last_text is not None:
        original = str(last_text)
        trimmed = original.rstrip()
        if trimmed != original:
            removed = original[len(trimmed) :]
            last_text.replace_with(NavigableString(trimmed))
            node.insert_after(NavigableString(removed))


def _normalize_inline_spacing(node: Tag) -> None:
    for child in node.children:
        if isinstance(child, Tag):
            _normalize_inline_spacing(child)

    previous: Tag | NavigableString | None = None
    for child in list(node.children):
        if isinstance(child, NavigableString):
            if node.name not in {"pre", "code"}:
                normalized = re.sub(r"[ \t\r\f\v]+", " ", str(child))
                if normalized != str(child):
                    child.replace_with(NavigableString(normalized))
                    child = node.contents[node.contents.index(previous) + 1] if previous in node.contents else child
            if previous is not None and _needs_space_between(previous, child):
                child.replace_with(NavigableString(f" {str(child)}"))
        elif isinstance(child, Tag):
            if previous is not None and _needs_space_between(previous, child):
                child.insert_before(NavigableString(" "))
        previous = child


def _needs_space_between(left: Tag | NavigableString, right: Tag | NavigableString) -> bool:
    left_text = _boundary_text(left, from_end=True)
    right_text = _boundary_text(right, from_end=False)
    if not left_text or not right_text:
        return False
    if left_text[-1].isspace() or right_text[0].isspace():
        return False
    if not ENDS_WITH_WORD_RE.search(left_text[-1]):
        return False
    if not STARTS_WITH_WORD_RE.search(right_text[0]):
        return False
    return True


def _boundary_text(node: Tag | NavigableString, *, from_end: bool) -> str:
    if isinstance(node, NavigableString):
        return str(node)
    text = node.get_text("", strip=False)
    return text


def _render_node(node: Tag | NavigableString) -> str:
    if isinstance(node, NavigableString):
        text = str(node).strip()
        return text if text else ""
    return str(node)


def _normalize_rendered_html(value: str) -> str:
    value = re.sub(r" {2,}<", " <", value)
    value = re.sub(r"> {2,}", "> ", value)
    return value


def _normalize_text_signature(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()
