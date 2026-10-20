"""Split a cleaned page into chunks of about 300 tokens, without ever separating a fact from its context.

How a page becomes chunks:
  1. split at '#'..'###' headings; each section remembers its heading path (the "crumbs")
  2. pack sections into chunks of about CHUNK_TARGET_CHARS; short sections are merged with the next one
  3. tables are never cut mid-row: a long table is split into row groups that each repeat the header row;
     a short title line just above a table ("Home Loans - Purchase") travels with it, and the
     "Rates are effective as of ..." line below a table stays in the table's chunk
  4. useful links (phone numbers, e-mail addresses, real page links) are appended to the chunk that
     mentions their link text
  5. each chunk gets a label with the page URL, page type and dates, which the answer step uses to
     decide which of two conflicting values is current
"""
from __future__ import annotations

import re

from .. import config
from ..cleaning import Link, header_date, page_type
from .chunk import Chunk

HEADING = re.compile(r"^(#{1,3}) +(.*)$")
FOOTNOTE = re.compile(r"(\d%|APR|APY)\d\b")            # footnote digit glued to a value: "1.23%4" -> "1.23%"
EFFECTIVE = re.compile(r"effective as of (\d{1,2}/\d{1,2}/\d{2,4})", re.I)

# --- links ------------------------------------------------------------------------------------------------
GENERIC_LINK_TEXT = {"read more", "keep reading", "learn more", "here", "click here", "apply today", "apply now",
                     "calculate", "see details", "continue", "get started", "admin", "more", "view all"}
USELESS_URL = re.compile(r"/(?:author|tag|category)/|/hubfs/|/hs-fs/|\.(?:png|jpe?g|gif|svg|webp)(?:$|\?)", re.I)


def useful_links(links: list[Link], page_url: str) -> list[tuple[str, str]]:
    """Links that carry information, as (text, target).

    Kept: site and external pages with meaningful link text, phone numbers ('tel:' -> 555-123-4567) and
    e-mail addresses - often hidden behind 'Call us' / 'Email us'. Dropped: author/tag pages, images,
    generic link text, links to the page itself, in-page anchors, duplicates; query strings are removed."""
    out, seen = [], set()
    own = page_url.split("?")[0].split("#")[0].rstrip("/")
    for link in links:
        text = link.text.strip().strip("*").strip()
        url = link.url.strip()
        if url.startswith("tel:"):
            digits = re.sub(r"\D", "", url)[-10:]
            if len(digits) != 10:
                continue
            url = f"{digits[:3]}-{digits[3:6]}-{digits[6:]}"
        elif url.startswith("mailto:"):
            url = url[7:].split("?")[0]
        elif url.startswith("http"):
            url = re.sub(r"\?.*$", "", url)
            if USELESS_URL.search(url) or url.split("#")[0].rstrip("/") == own:
                continue
        else:
            continue                                     # in-page anchors like '#top'
        if len(text) < 3 or text.lower() in GENERIC_LINK_TEXT or (text, url) in seen:
            continue
        seen.add((text, url))
        out.append((text, url))
    return out


# --- step 1: sections -------------------------------------------------------------------------------------
def split_sections(text: str) -> list[tuple[dict[int, str], list[str]]]:
    """[(heading path {level: heading}, body lines)] for each part of the page between headings.
    The heading lines themselves go into the path (later the crumbs), not into the body."""
    path: dict[int, str] = {}
    sections, current = [], []
    for line in text.split("\n"):
        m = HEADING.match(line)
        if m:
            if current:
                sections.append((dict(path), current))
            level = len(m.group(1))
            path = {k: v for k, v in path.items() if k < level}
            path[level] = m.group(2).strip()
            current = []
        else:
            current.append(line)
    if current:
        sections.append((dict(path), current))
    return sections


# --- step 2/3: packing, with tables kept whole --------------------------------------------------------------
def _blocks(lines: list[str]) -> list[tuple[str, list[str]]]:
    """Group lines into ('table', lines) for consecutive '|' lines or ('text', lines) for paragraphs."""
    out, current, is_table = [], [], False
    for line in lines + [""]:
        starts_table = line.startswith("|")
        if not line.strip() or (current and starts_table != is_table):
            if current:
                out.append(("table" if is_table else "text", current))
            current = [line] if line.strip() else []
            is_table = starts_table
        else:
            current.append(line)
            is_table = starts_table
    return out


def _is_table_title(blocks: list, b: int) -> bool:
    """A one-line text block of <= 60 chars that doesn't end like a sentence and is followed by a table
    (possibly through another such title line) - e.g. 'Home Loans' / 'Home Loans - Purchase'."""
    kind, lines = blocks[b]
    if kind != "text" or len(lines) != 1:
        return False
    if len(lines[0].strip()) > 60 or lines[0].rstrip().endswith((".", "!", "?", ":")):
        return False
    nxt = blocks[b + 1] if b + 1 < len(blocks) else None
    return bool(nxt) and (nxt[0] == "table" or _is_table_title(blocks, b + 1))


def _split_table(rows: list[str]) -> list[list[str]]:
    """Split a long table into pieces of <= CHUNK_MAX_CHARS that each start with the header + separator rows."""
    head, body = rows[:2], rows[2:]
    pieces, current = [], []
    for row in body:
        if current and sum(len(x) for x in head + current + [row]) > config.CHUNK_MAX_CHARS:
            pieces.append(head + current)
            current = []
        current.append(row)
    return pieces + [head + current] if current else pieces


def pack_sections(sections) -> list[tuple[dict[int, str], str]]:
    """Pack sections into chunk bodies of about CHUNK_TARGET_CHARS: [(heading path, body text)]."""
    packed: list[tuple[dict[int, str], str]] = []
    buf: list[str] = []
    buf_path: dict[int, str] = {}

    def flush() -> None:
        body = "\n\n".join(buf).strip()
        if body:
            packed.append((buf_path, body))
        buf.clear()

    for sec_path, lines in sections:
        if buf and sum(map(len, buf)) >= config.CHUNK_MIN_CHARS:
            flush()
        if not buf:
            buf_path = sec_path
        blocks = _blocks(lines)
        for b, (kind, block_lines) in enumerate(blocks):
            if _is_table_title(blocks, b):
                continue                                  # added in front of its table below
            titles = []
            if kind == "table":
                t = b - 1
                while t >= 0 and _is_table_title(blocks, t):
                    titles.insert(0, blocks[t][1][0])
                    t -= 1
            too_long = kind == "table" and len("\n".join(block_lines)) > config.CHUNK_MAX_CHARS
            for piece in (_split_table(block_lines) if too_long else [block_lines]):
                text = "\n\n".join(titles + ["\n".join(piece)])
                # an "effective as of" line right after a table stays in the table's chunk
                glue = kind == "text" and EFFECTIVE.search(text) and buf and buf[-1].startswith("|")
                if buf and not glue and sum(map(len, buf)) + len(text) > config.CHUNK_TARGET_CHARS:
                    flush()
                    buf_path = sec_path
                buf.append(text)
    flush()
    return packed


# --- step 4: links ----------------------------------------------------------------------------------------
def attach_links(packed, links: list[Link], page_url: str):
    """Append each useful link to the first chunk whose text mentions its link text (else the first chunk)."""
    link_lines: dict[int, list[str]] = {}
    for text, target in useful_links(links, page_url):
        i = next((n for n, (_, body) in enumerate(packed) if text in body), 0)
        link_lines.setdefault(i, []).append(f"{text} → {target}")
    return [(path, body + ("\n\nLinks: " + " · ".join(link_lines[n]) if n in link_lines else ""))
            for n, (path, body) in enumerate(packed)]


# --- step 5: the whole page -------------------------------------------------------------------------------
def chunk_page(url: str, title: str, text: str, fetched: str, links: list[Link] | None = None) -> list[Chunk]:
    """All chunks of one cleaned page."""
    ptype, published = page_type(url), header_date(text)
    text = FOOTNOTE.sub(r"\1", text)
    packed = attach_links(pack_sections(split_sections(text)), links or [], url)
    page_title = title.split(" | ")[0]
    chunks = []
    for path, body in packed:
        effective = sorted(set(EFFECTIVE.findall(body)))
        label = (f"[Source: {url} | {ptype} | fetched {fetched[:10]}"
                 + (f" | published {published}" if published else "")
                 + (f" | effective {', '.join(effective)}" if effective else "") + "]")
        crumbs = " > ".join([page_title] + [path[k] for k in sorted(path)])
        chunks.append(Chunk(url=url, label=label, page_type=ptype, crumbs=crumbs, body=body,
                            published=published, effective=effective))
    return chunks
