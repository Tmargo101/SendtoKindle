from __future__ import annotations

import unittest

from send_to_kindle.services.epub import _format_published_at


class EpubFormattingTests(unittest.TestCase):
    def test_format_published_at_date_only(self) -> None:
        self.assertEqual(_format_published_at("2026-04-12"), "April 12, 2026")

    def test_format_published_at_datetime_converts_to_pacific_daylight_time(self) -> None:
        self.assertEqual(
            _format_published_at("2026-04-11T17:18:22+00:00"),
            "April 11, 2026 at 10:18 AM PDT",
        )

    def test_format_published_at_datetime_converts_to_pacific_standard_time(self) -> None:
        self.assertEqual(
            _format_published_at("2026-01-11T17:18:22+00:00"),
            "January 11, 2026 at 9:18 AM PST",
        )

    def test_format_published_at_returns_original_when_unparseable(self) -> None:
        self.assertEqual(_format_published_at("April-ish 2026"), "April-ish 2026")
