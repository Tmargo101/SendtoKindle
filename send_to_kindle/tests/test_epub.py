from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ebooklib import epub

from send_to_kindle.models import ArticleContent
from send_to_kindle.services.epub import generate_epub


class EpubTests(unittest.TestCase):
    def test_generate_epub_writes_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            article = ArticleContent(
                source_url="https://example.com/article",
                title="Example Article",
                author="Author",
                site_name="Example",
                published_at="2026-04-12",
                content_html="<p>Hello world</p>",
                lead_image_url=None,
            )
            path = generate_epub(article, Path(temp_dir))
            self.assertTrue(path.exists())
            self.assertEqual(path.suffix, ".epub")
            book = epub.read_epub(str(path))
            self.assertEqual(book.get_metadata("DC", "title")[0][0], "Example Article")

    def test_generate_epub_includes_formatted_article_body(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            article = ArticleContent(
                source_url="https://example.com/article",
                title="Example Article",
                author="Author",
                site_name="Example",
                published_at="2026-04-12",
                content_html="<h2>Section</h2><p><strong>Bold</strong> <i>italic</i> <u>underline</u> <del>gone</del></p>",
                lead_image_url=None,
            )
            path = generate_epub(article, Path(temp_dir))
            book = epub.read_epub(str(path))

            chapter = next(item for item in book.get_items() if item.get_name() == "article.xhtml")
            content = chapter.get_content().decode("utf-8")

            self.assertIn("<h2>Section</h2>", content)
            self.assertIn("<strong>Bold</strong>", content)
            self.assertIn("<i>italic</i>", content)
            self.assertIn("<u>underline</u>", content)
            self.assertIn("<del>gone</del>", content)

    def test_generate_epub_adds_preformatted_text_styles(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            article = ArticleContent(
                source_url="https://example.com/article",
                title="Example Article",
                author="Author",
                site_name="Example",
                published_at="2026-04-12",
                content_html="<pre>Create an interactive HTML calculator that converts monthly expenses into annual projections.</pre>",
                lead_image_url=None,
            )
            path = generate_epub(article, Path(temp_dir))
            book = epub.read_epub(str(path))

            chapter = next(item for item in book.get_items() if item.get_name() == "article.xhtml")
            content = chapter.get_content().decode("utf-8")

            self.assertIn("white-space: pre-wrap;", content)
            self.assertIn("overflow-wrap: anywhere;", content)
            self.assertIn("<pre style=", content)
