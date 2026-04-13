from __future__ import annotations

from datetime import datetime
import imghdr
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Optional
from zoneinfo import ZoneInfo

from ebooklib import epub

from send_to_kindle.models import ArticleContent


PACIFIC_TIMEZONE = ZoneInfo("America/Los_Angeles")


def generate_epub(article: ArticleContent, output_dir: Path, lead_image: Optional[tuple[bytes, str]] = None) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)

    book = epub.EpubBook()
    book.set_identifier(article.source_url)
    book.set_title(article.title)
    book.set_language("en")
    if article.author:
        book.add_author(article.author)

    intro_lines = [f"<p><strong>Source:</strong> <a href=\"{article.source_url}\">{article.source_url}</a></p>"]
    if article.site_name:
        intro_lines.append(f"<p><strong>Site:</strong> {article.site_name}</p>")
    if article.published_at:
        intro_lines.append(f"<p><strong>Published:</strong> {_format_published_at(article.published_at)}</p>")

    body_html = "\n".join(intro_lines) + article.content_html
    chapter = epub.EpubHtml(title=article.title, file_name="article.xhtml", lang="en")
    chapter.content = f"<h1>{article.title}</h1>{body_html}"
    book.add_item(chapter)

    if lead_image is not None:
        image_bytes, content_type = lead_image
        image_name = _image_name(content_type, image_bytes)
        if image_name:
            book.set_cover(image_name, image_bytes)

    book.toc = (chapter,)
    book.spine = [chapter]
    book.add_item(epub.EpubNav())
    book.add_item(epub.EpubNcx())

    safe_stem = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in article.title.lower()).strip("-")
    if not safe_stem:
        safe_stem = "article"

    with NamedTemporaryFile(prefix=f"{safe_stem}-", suffix=".epub", dir=output_dir, delete=False) as handle:
        temp_path = Path(handle.name)

    epub.write_epub(str(temp_path), book)
    return temp_path


def _image_name(content_type: str, image_bytes: bytes) -> Optional[str]:
    subtype = content_type.split("/")[-1].split(";")[0].strip().lower()
    detected = imghdr.what(None, image_bytes)
    extension = detected or subtype
    if extension == "jpeg":
        extension = "jpg"
    if extension not in {"jpg", "png", "gif", "webp"}:
        return None
    return f"cover.{extension}"


def _format_published_at(value: str) -> str:
    parsed = _parse_published_at(value)
    if parsed is None:
        return value
    if parsed.hour == 0 and parsed.minute == 0 and parsed.second == 0 and "T" not in value.upper():
        return f"{parsed.strftime('%B')} {parsed.day}, {parsed.year}"

    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(PACIFIC_TIMEZONE)

    time_text = parsed.strftime("%I:%M %p").lstrip("0")
    timezone_text = parsed.strftime("%Z")
    if timezone_text:
        return f"{parsed.strftime('%B')} {parsed.day}, {parsed.year} at {time_text} {timezone_text}"
    return f"{parsed.strftime('%B')} {parsed.day}, {parsed.year} at {time_text}"


def _parse_published_at(value: str) -> Optional[datetime]:
    normalized = value.strip()
    if not normalized:
        return None

    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"

    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None
