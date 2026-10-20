"""Stage 1 - read the tables on every cleaned page (code only).

Two readers live here, because the later stages were built on two different ones and their results were
measured that way. Merging them would change what the LLM stages see, so that is a separate, measured change.

  outline_page()      -> used by the comparison stages (s4-s7). A page becomes sections (its heading path) with
                         the tables under each heading (line above, header row, rows) and every sentence that
                         contains a digit (where "effective as of" dates are found). Two tables printed directly
                         after each other, without a line between, are read as ONE table.

  labelling_tables()  -> used by the column-labelling stages (s2-s3). Every table instance with its section, its
                         title (the nearest short line above it), header row, nearest "effective as of" line and
                         rows. A row followed by a |---| separator always starts a new table, so two tables
                         printed directly after each other are read as TWO tables.
"""
from __future__ import annotations

import re

from ..cleaning import detailed_page_type, header_date, site_path


def cells(line: str) -> list[str]:
    """'| a | b |' -> ['a', 'b']."""
    return [c.strip() for c in line.strip().strip("|").split("|")]


# ============================================================================ reader 1: page outline (s4-s7)
OUTLINE_HEADING = re.compile(r"(#{1,6})\s+(.*)")
SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def _markdown_tables(text: str) -> list[tuple[list[str], list[list[str]]]]:
    """(header cells, data rows) for every block of '|' lines whose second line is a |---| separator."""
    lines, out, i = text.split("\n"), [], 0
    while i < len(lines):
        if lines[i].strip().startswith("|"):
            j = i
            while j < len(lines) and lines[j].strip().startswith("|"):
                j += 1
            block = [lines[k].strip() for k in range(i, j)]
            if len(block) >= 3 and set(block[1].replace(" ", "")) <= set("|-:"):
                out.append((cells(block[0]), [cells(r) for r in block[2:]]))
            i = j
        else:
            i += 1
    return out


def outline(text: str) -> list[dict]:
    """Sections of one page in page order: {"path": [headings], "tables": [...], "numbers": [sentences]}.
    A table is {"above": the last text line before it, "header": cells, "rows": first cells, "cells": rows}."""
    lines = text.split("\n")
    tables = iter(_markdown_tables(text))
    stack: list[tuple[int, str]] = []          # (heading level, heading text), outermost first
    sections: list[dict] = []
    last_text = ""

    def section() -> dict:
        path = [h for _, h in stack]
        if not sections or sections[-1]["path"] != path:
            sections.append({"path": path, "tables": [], "numbers": []})
        return sections[-1]

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        m = OUTLINE_HEADING.match(line)
        if m:
            level = len(m[1])
            stack = [(lv, h) for lv, h in stack if lv < level] + [(level, m[2].strip())]
            last_text = m[2].strip()
            i += 1
        elif line.startswith("|"):
            j = i
            while j < len(lines) and lines[j].strip().startswith("|"):
                j += 1
            if j - i >= 3 and set(lines[i + 1].replace(" ", "")) <= set("|-:"):
                header, rows = next(tables)
                section()["tables"].append({"above": last_text, "header": header,
                                            "rows": [r[0] for r in rows if r and r[0]], "cells": rows})
            i = j
        else:
            if line:
                last_text = line
                for sentence in SENTENCE_END.split(line):
                    if re.search(r"\d", sentence):
                        section()["numbers"].append(sentence.strip())
            i += 1
    return sections


def outline_page(snap: str, url: str, text: str, link: str = "") -> dict:
    """One page of one download, as the comparison stages read it. `link` is an optional pointer to the page's
    raw file, shown on review pages only."""
    return {"snap": snap, "page": site_path(url), "type": detailed_page_type(url), "article_date": header_date(text),
            "link": link, "sections": outline(text)}


# ============================================================================ reader 2: table instances (s2-s3)
LABEL_HEADING = re.compile(r"^(#{1,6})\s+(.*)")
EFFECTIVE_LINE = re.compile(r"effective as of", re.I)
TITLE_CHARS = 80            # a title is a line of at most this many characters
TITLE_LOOKBACK = 3          # how many recent lines above a table may hold its title
FOOTNOTE_MARK = re.compile(r"(?<=[A-Za-z)%])\d{1,2}(?=[\s|.,;:]|$)")      # 'APY)1' -> 'APY)'


def plain(text: str | None) -> str:
    """Text without markdown bold, backslash escapes and footnote markers, with single spaces."""
    return re.sub(r"\s+", " ", FOOTNOTE_MARK.sub("", (text or "").replace("**", "").replace("\\", ""))).strip()


def labelling_path(url: str) -> str:
    """Page path as the labelling stages show it: like site_path, without a trailing '/'."""
    return site_path(url).rstrip("/") or "/"


def labelling_page_type(url: str) -> str:
    """detailed_page_type, with product pages split into 'business' (the path mentions business) and 'personal'."""
    kind = detailed_page_type(url)
    if kind == "product":
        return "business" if "business" in labelling_path(url).split("?")[0].lower() else "personal"
    return kind


def _is_separator(line: str) -> bool:
    return set(line.replace(" ", "")) <= set("|-:") and "-" in line


def _has_text(line: str) -> bool:
    return bool(re.sub(r"[^a-z0-9]+", " ", line.lower()).strip())


def _blocks(text: str) -> list[dict]:
    """Ordered lines of a page (non-empty, stripped) as blocks: table rows carry their section path, title and
    header row; every block gets the nearest "effective as of" line (the first below it in its own section, else
    the first below it anywhere, else the last one above it - rate pages print it under each table)."""
    out, stack, recent, effective = [], [], [], []
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    i = 0
    while i < len(lines):
        line = lines[i]
        m = LABEL_HEADING.match(line)
        if m:
            level = len(m[1])
            stack = [(lv, h) for lv, h in stack if lv < level] + [(level, m[2].strip("*# ").strip())]
            recent = [m[2].strip("*# ").strip()]
            i += 1
            continue
        path = " > ".join(h for _, h in stack)
        if EFFECTIVE_LINE.search(line):
            effective.append((len(out), path, line))
        if line.startswith("|"):
            header = None
            title = next((x for x in reversed(recent) if len(x) <= TITLE_CHARS), recent[-1] if recent else "")
            j = i
            while j < len(lines) and lines[j].startswith("|"):
                row = lines[j]
                if j + 1 < len(lines) and _is_separator(lines[j + 1]):
                    header, j = row, j + 2                 # a header row: a new table starts here
                    continue
                if not _is_separator(row) and _has_text(row):
                    out.append({"text": row, "kind": "row", "path": path, "table": title, "header": header})
                j += 1
            i = j
            continue
        out.append({"text": line, "kind": "text", "path": path, "table": None, "header": None})
        recent = (recent + [line])[-TITLE_LOOKBACK:]
        i += 1
    for k, b in enumerate(out):
        b["i"] = k
        own_below = [t for pos, p, t in effective if p == b["path"] and pos > k]
        below = [t for pos, p, t in effective if pos > k]
        b["effective"] = (own_below or below or [t for _, _, t in effective[::-1]])[:1]
    return out


def _title_above(lines: list[str], first_row: str, section: str) -> str | None:
    """The nearest short line above a table that is not a list item, a table line or empty: the table's label.
    Stops at a heading (the heading itself is used when nothing closer qualifies)."""
    try:
        i = lines.index(first_row)
    except ValueError:
        return None
    for line in reversed(lines[:i]):
        if not line or line.startswith("|"):
            continue
        if line.startswith("#"):
            return plain(line.lstrip("#").strip("* "))
        if not line.startswith(("- ", "* ", "+ ")) and len(plain(line)) <= TITLE_CHARS:
            return plain(line)
    return None


def labelling_tables(snap: str, url: str, text: str) -> list[dict]:
    """Table instances of one page version: consecutive rows with the same section, title and header row.
    Each: {snap, page, type, section, title, header, effective, rows (raw lines)}."""
    out: list[dict] = []
    for b in _blocks(text):
        if b["kind"] != "row":
            continue
        key = (b["path"], b["table"], b["header"])
        if not out or out[-1]["_key"] != key or out[-1]["_last"] != b["i"] - 1:
            out.append({"_key": key, "snap": snap, "page": labelling_path(url), "type": labelling_page_type(url),
                        "section": b["path"], "title": b["table"], "header": b["header"],
                        "effective": (b["effective"] or [None])[0], "rows": []})
        out[-1]["rows"].append(b["text"])
        out[-1]["_last"] = b["i"]
    lines = [x.strip() for x in text.splitlines()]
    for t in out:
        del t["_key"], t["_last"]
        t["title"] = _title_above(lines, t["rows"][0], t["section"]) or t["title"]
    return out
