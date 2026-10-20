"""Tests for kb.retrieval: chunking keeps facts with their context; tokenising keeps numbers whole."""
from kb.cleaning import Link
from kb.retrieval.bm25 import BM25Index, tokens
from kb.retrieval.chunker import chunk_page, useful_links

URL = "https://www.dupaco.com/personal/example"
PAGE = """# Example Accounts

## Rates

Example Savings

| Tier | APY |
| --- | --- |
| $1 - $999.99 | 1.23%4 |

Rates are effective as of 01/02/2026.
"""


def test_table_keeps_title_and_effective_date_and_drops_footnote_digit():
    [chunk] = chunk_page(URL, "Example | Dupaco", PAGE, "2026-01-05T00:00:00Z")
    assert chunk.body.startswith("Example Savings\n\n| Tier | APY |")
    assert "| $1 - $999.99 | 1.23% |" in chunk.body                     # "1.23%4" -> "1.23%"
    assert "effective as of 01/02/2026" in chunk.body
    assert chunk.crumbs == "Example > Example Accounts > Rates"
    assert chunk.label == f"[Source: {URL} | product | fetched 2026-01-05 | effective 01/02/2026]"


def test_long_table_split_into_row_groups_that_repeat_the_header():
    rows = "\n".join(f"| row {i} with some padding text to make it long | {i}.00% |" for i in range(80))
    page = f"## Big\n\n| Name | Rate |\n| --- | --- |\n{rows}\n"
    chunks = chunk_page(URL, "Example", page, "2026-01-05")
    assert len(chunks) > 1
    assert all("| Name | Rate |\n| --- | --- |" in c.body for c in chunks)


def test_useful_links_keep_phone_and_email_drop_generic():
    links = [Link("Call us", "tel:+15551234567"), Link("Email us", "mailto:help@example.com?subject=x"),
             Link("Learn more", "https://www.dupaco.com/x"), Link("Our rates", "https://www.dupaco.com/rates?a=1")]
    assert useful_links(links, URL) == [("Call us", "555-123-4567"), ("Email us", "help@example.com"),
                                        ("Our rates", "https://www.dupaco.com/rates")]


def test_tokens_keep_numbers_whole_and_stem_plurals():
    assert tokens("What are the fees for IRAs at 1.23% on $9,999?") == ["fee", "ira", "1.23%", "$9,999"]


def test_bm25_ranks_rare_word_match_first():
    index = BM25Index(["savings rate", "checking rate", "rare widget rate"])
    assert index.rank("widget")[0] == 2
