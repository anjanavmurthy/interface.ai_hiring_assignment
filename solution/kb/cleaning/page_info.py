"""Facts about a page that the answer step uses to judge how current and how official it is."""
from __future__ import annotations

import re

from .site_rules import DETAILED_PAGE_TYPES, PAGE_TYPES

MIN_READ = re.compile(r"^\d+ min read$")
DATE_LINE = re.compile(r"^(?:January|February|March|April|May|June|July|August|September|October|November|December)"
                       r" \d{1,2}, \d{4}$", re.I)


def page_type(url: str) -> str:
    """'rates', 'product', 'news', 'blog/article', 'calculator', ... from the URL (first matching pattern)."""
    return next(name for name, pattern in PAGE_TYPES if pattern.search(url))


def header_date(text: str) -> str | None:
    """The publish date in an article header, e.g. 'April 06, 2026', or None if the page has no header.

    Articles start with 'N min read', then the author, then the date, within the first few lines."""
    lines = [line.strip() for line in text.split("\n") if line.strip()][:6]
    if not lines or not MIN_READ.match(lines[0]):
        return None
    return next((line for line in lines if DATE_LINE.match(line)), None)


SITE = "https://www.dupaco.com"


def site_path(url: str) -> str:
    """'https://www.dupaco.com/rates' -> '/rates' (the home page -> '/')."""
    return url.removeprefix(SITE) or "/"


def detailed_page_type(url: str) -> str:
    """The finer page type the conflicts stages use (site_rules.DETAILED_PAGE_TYPES, first match on the path)."""
    path = site_path(url)
    return next(name for name, _what, pattern in DETAILED_PAGE_TYPES if re.search(pattern, path))
