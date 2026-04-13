from __future__ import annotations

import unittest
from unittest.mock import patch

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

    def test_extract_article_retains_subheadings_and_inline_formatting(self) -> None:
        html = """
        <html>
          <body>
            <article>
              <h1>Visible Article Headline</h1>
              <h2>Section Heading</h2>
              <p>
                Keeps <strong>bold</strong>, <em>italic</em>,
                <u>underline</u>, and <del>strikethrough</del>
                formatting.
              </p>
            </article>
          </body>
        </html>
        """

        article = extract_article(html, "https://example.com/article")

        self.assertNotIn("<h1>Visible Article Headline</h1>", article.content_html)
        self.assertIn("<h2>Section Heading</h2>", article.content_html)
        self.assertIn("<strong>bold</strong>", article.content_html)
        self.assertIn("<i>italic</i>", article.content_html)
        self.assertIn("<u>underline</u>", article.content_html)
        self.assertIn("<del>strikethrough</del>", article.content_html)

    def test_extract_article_repairs_split_formatted_paragraphs(self) -> None:
        html = """
        <html>
          <body>
            <article>
              <h1>Claude.</h1>
              <p>
                <span>See, I’ve been writing about AI for three years. So people often ask me, “Ruben, I’ve seen your newsletter about [tool], but do you really use it?” If I </span><em>write</em><span> about it, I </span><em>do </em><span>use it.</span>
              </p>
              <p>
                <span>And right now, in February 2026, Claude is the single most important AI tool for anyone doing knowledge work.</span>
              </p>
            </article>
          </body>
        </html>
        """

        article = extract_article(html, "https://example.com/article")

        self.assertIn('If I <i>write</i> about it, I <i>do</i> use it.', article.content_html)
        self.assertIn("And right now, in February 2026", article.content_html)
        self.assertNotIn("If I </p>", article.content_html)

    def test_extract_article_repairs_ordered_list_items_with_inline_links(self) -> None:
        source_html = """
        <html>
          <body>
            <article>
              <h1>Claude.</h1>
              <h4>How to install Cowork:</h4>
              <ol>
                <li><p><span>Go to </span><a href="https://claude.com/download">claude.com/download</a><span>. Download the app.</span></p></li>
                <li><p><span>Open the app. Click the </span><strong>Cowork</strong><span> tab at the top.</span></p></li>
                <li><p><span>Pro tip: create markdown files about </span><a href="https://example.com/you">you</a><span> - or anything you </span><strong><a href="https://example.com/want">want</a></strong><span>.</span></p></li>
              </ol>
            </article>
          </body>
        </html>
        """
        cleaned_html = """
        <html>
          <body>
            <h4>How to install Cowork:</h4>
            <ul>
              <li><p>Go to</p><a href="https://claude.com/download">claude.com/download</a>. Download the app.</li>
              <li><p>Open the app. Click the</p><strong>Cowork</strong>tab at the top.</li>
              <li><p>Pro tip: create markdown files about</p><a href="https://example.com/you">you</a>- or anything you<strong/>.<a href="https://example.com/want">want</a></li>
            </ul>
          </body>
        </html>
        """

        with patch("send_to_kindle.services.extractor.trafilatura.extract", return_value=cleaned_html):
            article = extract_article(source_html, "https://example.com/article")

        self.assertIn("<ol>", article.content_html)
        self.assertNotIn("<ul>", article.content_html)
        self.assertIn('Go to <a href="https://claude.com/download">claude.com/download</a>. Download the app.', article.content_html)
        self.assertIn("Open the app. Click the <strong>Cowork</strong> tab at the top.", article.content_html)
        self.assertIn('Pro tip: create markdown files about <a href="https://example.com/you">you</a> - or anything you <strong><a href="https://example.com/want">want</a></strong>.', article.content_html)

    def test_extract_article_collapses_nested_pre_blocks(self) -> None:
        source_html = """
        <html>
          <body>
            <article>
              <h1>Claude.</h1>
              <h4>Your first prompt:</h4>
              <pre><code><code>I want to [YOUR TASK] so that [WHAT SUCCESS LOOKS LIKE].

First, read the uploaded files completely before responding.

Only begin work once we’ve aligned.</code></code></pre>
            </article>
          </body>
        </html>
        """
        cleaned_html = """
        <html>
          <body>
            <h4>Your first prompt:</h4>
            <pre>
              <pre>
                <pre>I want to [YOUR TASK] so that [WHAT SUCCESS LOOKS LIKE].

First, read the uploaded files completely before responding.

Only begin work once we’ve aligned.</pre>
              </pre>
            </pre>
          </body>
        </html>
        """

        with patch("send_to_kindle.services.extractor.trafilatura.extract", return_value=cleaned_html):
            article = extract_article(source_html, "https://example.com/article")

        self.assertIn("<pre>I want to [YOUR TASK] so that [WHAT SUCCESS LOOKS LIKE].", article.content_html)
        self.assertNotIn("<pre>\n <pre>", article.content_html)
        self.assertNotIn("</pre>\n </pre>", article.content_html)
