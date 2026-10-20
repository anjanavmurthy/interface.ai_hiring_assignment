"""Small text helpers shared by the conflict stages: tidy a table cell, compare values, key a header row."""
from __future__ import annotations

import re


def clean(s: str | None) -> str:
    """A cell as plain text: link targets, bold/italic markers and escapes removed, dashes unified, single spaces."""
    return re.sub(r"\s+", " ", re.sub(r"\]\([^)]*\)|[*_\\]", "", s or "")).replace("–", "-").replace("—", "-").strip()


def norm_value(cell: str) -> str:
    """A value in comparable form; number formatting is ignored: trailing zeros after the point, zero written with
    or without decimals or a percent sign, footnote digits after a value, and a trailing 'APR' word."""
    x = re.sub(r"\s*APR\s*\d?$", "", clean(cell))
    x = re.sub(r"(?<=%)\s*\d{1,2}$", "", x)
    if re.fullmatch(r"[$]?0+(\.0+)?%?", x):
        return "0"
    return re.sub(r"\d[\d,]*(?:\.\d+)?", lambda m: f"{float(m[0].replace(',', '')):g}", x)


def header_key(header_cells: list[str]) -> str:
    """A header row as a lookup key: cleaned, lowercased, a footnote digit at the end of a cell removed."""
    return " | ".join(re.sub(r"(?<=[A-Za-z)%])\s?\d{1,2}$", "", clean(c)).lower() for c in header_cells)
