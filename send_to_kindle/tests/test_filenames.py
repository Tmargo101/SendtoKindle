from __future__ import annotations

import unittest

from send_to_kindle.filenames import build_epub_filename


class FilenameTests(unittest.TestCase):
    def test_build_epub_filename_preserves_spaces_and_caps(self) -> None:
        filename = build_epub_filename("Sam Altman responds to ‘incendiary’ New Yorker article after attack on his home")

        self.assertEqual(
            filename,
            "Sam Altman responds to 'incendiary' New Yorker article after attack on his home.epub",
        )

    def test_build_epub_filename_removes_invalid_characters(self) -> None:
        filename = build_epub_filename('Title: Draft/Review? <Final>* | Version\\2')

        self.assertEqual(filename, "Title DraftReview Final Version2.epub")

