"""Page cleaning: remove website noise from a page's markdown, keep every piece of real content.

Each rule is one small function that takes text and returns (new_text, removed_pieces), so it can be tested
and measured on its own. `clean_page` applies them in a fixed order.

    R1 teaser sections   blocks of cards linking to other articles (they repeat other pages' titles/dates)
    R2 pop-up modal      the "you are leaving our site" warning
    R3 images            image markdown (alt texts are icon names, not content)
    R4 link URLs         "[text](url)" -> "text"; the URLs are returned separately, never lost
    R5 widgets           captcha / chat widget leftovers, carousel buttons, tables with no text (widget grids)
    R6 country list      the phone country-code dropdown (~240 lines per form page)
    R7 form chrome       required-field labels, "Submit", form hints
    R8 listing pages     tag/author/category pages, skipped as a whole (see is_listing_page)
    R9 formatting        escaped line breaks, invisible characters, separator lines, extra blank lines

Rules never touch tables, "effective as of" lines, FAQ headings or the article header date - the facts and
dates the answer step relies on.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field

from . import site_rules as site

# --- generic markdown / text patterns ---------------------------------------------------------------------
HEADING_1_3 = re.compile(r"^(#{1,3}) ")
SECTION_HEADING = re.compile(r"^#{2,3} ")
URL = r"(?:[^()\s]|\([^()\s]*\))+"       # a URL may contain one level of brackets: ".../Sheet-11(Money).csv"
IMAGE = re.compile(r"!\[[^\]]*\]\(" + URL + r"(?:\s+\"[^\"]*\")?\)")
LINK = re.compile(r"\[([^\]]*)\]\((" + URL + r")(?:\s+\"[^\"]*\")?\)")
HARD_BREAK = re.compile(r"[ \t]*\\\\[ \t]*$", re.M)   # markdown line-break marker "\\" at a line end
FOOTNOTE_REF = re.compile(r"\d{1,2}")                  # link text of a footnote reference: "[1](...#fine-print)"
COUNTRY_LINE = re.compile(r"^- [\U0001F1E6-\U0001F1FF]{2}\s.*\+\d{1,5}\s*$")   # "- 🇦🇫 Afghanistan (...) +93"
FLAG_ONLY = re.compile(r"^(?:[\U0001F1E6-\U0001F1FF]{2}\s*)+$")
ESCAPED_CRLF = re.compile(r"\\+r\\+n")                 # literal "\r\n" text left by the crawler
EMPTY_TABLE_TEXT = re.compile(r"[^|\s:\-]")              # any character that is not table markup
SEPARATOR = re.compile(r"^[ \t]*(?:\\?# # #|\* \* \*)[ \t]*$", re.M)   # press-release end mark, horizontal rule
INVISIBLE = re.compile("[​‌‍‎‏‪‫‬‭‮⁠﻿]")
NBSP = " "

RULES = ["R1_teaser_sections", "R2_popups", "R3_images", "R4_link_urls", "R5_widgets",
         "R6_country_list", "R7_form_chrome", "R8_listing_pages", "R9_formatting"]


@dataclass(frozen=True)
class Link:
    """A link taken out of the text: its visible text and where it pointed."""
    text: str
    url: str


@dataclass
class CleanedPage:
    text: str                                                     # the cleaned markdown
    links: list[Link]                                             # every link removed from the text (R4)
    removed: dict[str, list] = field(default_factory=dict)        # rule -> removed pieces (for review tools)
    chars_removed: dict[str, int] = field(default_factory=dict)   # rule -> characters removed


# --- helpers ----------------------------------------------------------------------------------------------
def _drop_lines(text: str, should_drop) -> tuple[str, list[str]]:
    """Remove every line for which should_drop(stripped line) is true; return (kept text, removed lines)."""
    kept, removed = [], []
    for line in text.split("\n"):
        (removed if should_drop(line.strip()) else kept).append(line)
    return "\n".join(kept), removed


# --- rules ------------------------------------------------------------------------------------------------
def _next_line(lines: list[str], i: int, end: int) -> int | None:
    """Index of the first non-blank line after line i and before `end`, or None."""
    return next((j for j in range(i + 1, end) if lines[j].strip()), None)


def _teaser_end(lines: list[str], start: int, end: int) -> int | None:
    """The last line of the teaser cards in lines[start:end], or None if they hold fewer than two cards.

    Article layout: cards end with a 'Read More' / 'Keep reading' link; the last such link ends the block.
    Dated layout: '[**title**](url)', short date, summary; the block ends after the last summary and the
    'Read more ...' / 'See all ...' link that may follow it."""
    body = range(start, end)
    cards = [i for i in body if site.TEASER_CARD_TITLE.match(lines[i])]
    reads = [i for i in body if site.TEASER_READ_MORE.match(lines[i])]
    if len(cards) >= 2 and len(reads) >= 2:
        return reads[-1]
    dates = []                                                       # the date line of each dated card
    for i in body:
        j = _next_line(lines, i, end) if site.TEASER_BOLD_TITLE.match(lines[i]) else None
        if j is not None and site.TEASER_SHORT_DATE.match(lines[j].strip()):
            dates.append(j)
    if len(dates) < 2:
        return None
    summary = _next_line(lines, dates[-1], end)
    last = dates[-1] if summary is None else summary
    more = _next_line(lines, last, end)
    return more if more is not None and site.TEASER_MORE_LINK.match(lines[more].strip()) else last


def remove_teaser_sections(text: str) -> tuple[str, list[str]]:
    """R1. Remove '##'/'###' sections made of at least two teaser cards (in either of the site's two card
    layouts, see _teaser_end), from the heading through the end of the last card. Anything after that inside
    the section (e.g. an FAQ) is kept."""
    lines = text.split("\n")
    starts = [i for i, line in enumerate(lines) if HEADING_1_3.match(line)] + [len(lines)]
    drop, removed = set(), []
    for start, end in zip(starts, starts[1:]):
        if not SECTION_HEADING.match(lines[start]):
            continue
        last = _teaser_end(lines, start + 1, end)
        if last is not None:
            drop.update(range(start, last + 1))
            removed.append("\n".join(lines[start:last + 1]))
    if not drop:
        return text, []
    return "\n".join(line for i, line in enumerate(lines) if i not in drop), removed


def remove_popups(text: str) -> tuple[str, list[str]]:
    """R2. External-link warning modal: close button, 'Heads up!...', 'We only do this...', 'Continue / Cancel'."""
    return _drop_lines(text, lambda s: s in site.POPUP_LINES
                       or s.startswith(site.POPUP_PREFIXES)
                       or bool(site.POPUP_CONTINUE.match(s)))


def strip_images(text: str) -> tuple[str, list[str]]:
    """R3. Remove '![alt](img)'. In a linked image '[![alt](img)](link)' only the image goes; the outer link
    (and any button label inside it) is then handled by R4, so its URL is kept."""
    return IMAGE.sub("", text), IMAGE.findall(text)


def strip_links(text: str) -> tuple[str, list[Link]]:
    """R4. '[text](url)' -> 'text', returning every (text, url) so no URL is lost.

    A link whose text is only a number is a footnote reference ('$300 [1](...#fine-print)'). It is removed
    from the text entirely, otherwise the number would be glued onto the value before it ('$3001')."""
    links: list[Link] = []

    def keep_text(match: re.Match) -> str:
        label = match.group(1)
        links.append(Link(text=HARD_BREAK.sub("", label).strip(), url=match.group(2)))
        return "" if FOOTNOTE_REF.fullmatch(label.strip("* ")) else label

    return LINK.sub(keep_text, text), links


def _drop_empty_tables(text: str) -> tuple[str, list[str]]:
    """Remove tables in which no cell holds any text (widget grids such as a captcha's image grid). Images count as
    no text: this runs before R3 strips them, and a grid of images would otherwise be left as an empty table."""
    lines, kept, removed, i = text.split("\n"), [], [], 0
    while i < len(lines):
        if not lines[i].lstrip().startswith("|"):
            kept.append(lines[i])
            i += 1
            continue
        j = i
        while j < len(lines) and lines[j].lstrip().startswith("|"):        # the whole table block
            j += 1
        block = lines[i:j]
        if EMPTY_TABLE_TEXT.search(IMAGE.sub("", "".join(block))):
            kept.extend(block)
        else:
            removed.append("\n".join(block))
        i = j
    return "\n".join(kept), removed


def remove_widgets(text: str) -> tuple[str, list[str]]:
    """R5. Captcha / chat widget leftovers (exact lines, the captcha challenge line, the visitor's IP address) and
    tables with no text in any cell (the captcha's image grid)."""
    text, lines = _drop_lines(text, lambda s: s in site.WIDGET_LINES or bool(site.CAPTCHA_CHALLENGE.match(s))
                                   or bool(site.VISITOR_IP.match(s)))
    text, grids = _drop_empty_tables(text)
    return text, lines + grids


def remove_country_list(text: str) -> tuple[str, list[str]]:
    """R6. Phone country-code dropdown lines and lone flag lines."""
    return _drop_lines(text, lambda s: bool(COUNTRY_LINE.match(s) or FLAG_ONLY.match(s)))


def remove_form_chrome(text: str) -> tuple[str, list[str]]:
    """R7. Required-field labels ('... (Required)', '...?\\*', 'First Name\\*'), 'Submit', form hints and
    consent text."""
    return _drop_lines(text, lambda s: s in site.FORM_LINES
                       or bool(site.FORM_REQUIRED_SUFFIX.search(s))
                       or bool(site.FORM_REQUIRED_QUESTION.search(s))
                       or bool(site.FORM_FIELD.match(s))
                       or s.startswith(site.FORM_PREFIXES))


def normalize_crlf(text: str) -> str:
    """R9, part 1 (runs first): literal '\\r\\n' leftovers become a space."""
    return ESCAPED_CRLF.sub(" ", text)


def normalize_text(text: str) -> str:
    """R9, part 2 (runs last): invisible characters, non-breaking spaces, '\\\\' line-break markers,
    separator lines ('# # #', '* * *'), trailing spaces and runs of blank lines."""
    text = INVISIBLE.sub("", text).replace(NBSP, " ").replace("\r\n", "\n")
    text = SEPARATOR.sub("", HARD_BREAK.sub("", text))
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"


def is_listing_page(url: str) -> bool:
    """R8. Tag / author / category pages only list other pages; they are skipped whole."""
    return bool(site.LISTING_URL.search(url))


# --- the pipeline -----------------------------------------------------------------------------------------
def clean_page(text: str) -> CleanedPage:
    """Apply all rules in an order where each still sees what it needs: teaser cards and the pop-up
    'Continue' line are matched while their links are still present, so R4 runs after them."""
    removed: dict[str, list] = defaultdict(list)
    sizes: dict[str, int] = {}

    def step(rule: str, fn, current: str) -> str:
        before = len(current)
        current, pieces = fn(current)
        sizes[rule] = sizes.get(rule, 0) + before - len(current)
        removed[rule].extend(pieces)
        return current

    before = len(text)
    text = normalize_crlf(text)
    sizes["R9_formatting"] = before - len(text)
    text = step("R1_teaser_sections", remove_teaser_sections, text)
    text = step("R2_popups", remove_popups, text)
    text = step("R5_widgets", remove_widgets, text)
    text = step("R6_country_list", remove_country_list, text)
    text = step("R7_form_chrome", remove_form_chrome, text)
    text = step("R3_images", strip_images, text)
    before = len(text)
    text, links = strip_links(text)
    sizes["R4_link_urls"] = before - len(text)
    before = len(text)
    text = normalize_text(text)
    sizes["R9_formatting"] += before - len(text)
    return CleanedPage(text=text, links=links, removed=dict(removed), chars_removed=sizes)


# --- teaser cards (kept for review tools: some carry the only copy of an article's date) ------------------
TEASER_DATE = re.compile(r"^(?:January|February|March|April|May|June|July|August|September|October|November|December)"
                         r" \d{1,2}, \d{4}$")
TEASER_TITLE = re.compile(r"^#### \[(.+)\]\((\S+)\)\s*$")


def parse_teaser_cards(block: str) -> list[dict]:
    """What a removed teaser section said about each linked article: title, url, date, summary."""
    cards, date = [], None
    lines = [line.strip() for line in block.split("\n")]
    for i, line in enumerate(lines):
        if TEASER_DATE.match(line):
            date = line
        m = TEASER_TITLE.match(line)
        if m:
            summary = next((s for s in lines[i + 1:] if s and not site.TEASER_READ_MORE.match(s)), "")
            if summary.startswith(("#", "[", "!")):
                summary = ""
            cards.append({"title": m.group(1), "url": m.group(2), "date": date, "summary": summary})
            date = None
    return cards
