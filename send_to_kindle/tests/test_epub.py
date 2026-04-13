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
