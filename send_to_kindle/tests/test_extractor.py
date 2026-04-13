from __future__ import annotations

import unittest

from send_to_kindle.services.extractor import extract_article


class ExtractorTests(unittest.TestCase):
    def test_extract_article_prefers_page_h1_for_title(self) -> None:
        html = """
        <html>
          <head>
            <title>Browser Title</title>
            <meta property="og:title" content="Open Graph Title" />
          </head>
          <body>
            <article>
              <h1>Visible Article Headline</h1>
              <p>First paragraph.</p>
              <p>Second paragraph.</p>
            </article>
          </body>
        </html>
        """

        article = extract_article(html, "https://example.com/article")

        self.assertEqual(article.title, "Visible Article Headline")

