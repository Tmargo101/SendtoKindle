from __future__ import annotations

import unicodedata


INVALID_FILENAME_CHARACTERS = {"<", ">", ":", "\"", "/", "\\", "|", "?", "*"}
ASCII_PUNCTUATION_MAP = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": "\"",
        "\u201d": "\"",
        "\u2013": "-",
        "\u2014": "-",
        "\u2026": "...",
    }
)


def build_epub_filename(title: str) -> str:
    ascii_title = _normalize_ascii_punctuation(title)
    cleaned = "".join(char for char in ascii_title if char not in INVALID_FILENAME_CHARACTERS)
    cleaned = " ".join(cleaned.split()).strip().rstrip(".")
    if not cleaned:
        cleaned = "Article"
    return f"{cleaned}.epub"


def _normalize_ascii_punctuation(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.translate(ASCII_PUNCTUATION_MAP))
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return ascii_text
