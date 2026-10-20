"""Tests for kb.cleaning: small hand-written pages for each rule, plus one check on the real snapshots."""
import json
from pathlib import Path

import pytest
from scoring import contains

from kb.cleaning import Link, clean_page, header_date, is_listing_page
from kb.cleaning import cleaner as c

ROOT = Path(__file__).resolve().parents[1]

TEASER_THEN_FAQ = """# Business Checking

Intro text that must stay.

## Handpicked for You

[![Card one](https://www.dupaco.com/hubfs/a.png)](https://www.dupaco.com/learn/blog/one)

1 min read

April 01, 2021

#### [Card one title](https://www.dupaco.com/learn/blog/one)

Summary of card one.

[Keep reading](https://www.dupaco.com/learn/blog/one)

#### [Card two title](https://www.dupaco.com/newsroom/two)

Summary of card two.

[Keep reading](https://www.dupaco.com/newsroom/two)

## Frequently Asked Questions

- [Is my account insured?](https://www.dupaco.com/business/checking-accounts#)

Yes. Insured up to $250,000 per account.
"""

DATED_TEASER_THEN_FAQ = """# Example Product

Product text that must stay.

## Handpicked for You

[Card one title](https://www.dupaco.com/learn/blog/one)

[**Card one title**](https://www.dupaco.com/learn/blog/one)

Jan 2, 2026

The first lines of card one, cut off...

[Card two title](https://www.dupaco.com/learn/blog/two)

[**Card two title**](https://www.dupaco.com/learn/blog/two)

Feb 3, 2025

The first lines of card two, cut off...

[Read more money tips](https://www.dupaco.com/resources)

## Frequently Asked Questions

Answer that must stay.
"""

BOLD_FEATURE_LINKS = """## Features

[**Feature one**](https://www.dupaco.com/example#one)

[**Feature two**](https://www.dupaco.com/example#two)

What the features do.
"""

STARTUP_COACHING = """## Free startup coaching

#### 1:1 on-demand coaching, provided by seasoned entrepreneurs.

#### [Sign up](https://calendly.com/business-coaching-team/dupaco-startup-coaching?month=2026-04)
"""


def test_teaser_removed_but_faq_after_it_kept():
    out, removed = c.remove_teaser_sections(TEASER_THEN_FAQ)
    assert "Handpicked" not in out and "Card one title" not in out and "Card two title" not in out
    assert "April 01, 2021" not in out
    assert "## Frequently Asked Questions" in out and "$250,000" in out
    assert "Intro text that must stay." in out
    assert len(removed) == 1


def test_teaser_cards_are_saved_before_removal():
    _, removed = c.remove_teaser_sections(TEASER_THEN_FAQ)
    assert c.parse_teaser_cards(removed[0]) == [
        {"title": "Card one title", "url": "https://www.dupaco.com/learn/blog/one", "date": "April 01, 2021",
         "summary": "Summary of card one."},
        {"title": "Card two title", "url": "https://www.dupaco.com/newsroom/two", "date": None,
         "summary": "Summary of card two."},
    ]


def test_old_recent_news_heading_is_removed_too():
    out, _ = c.remove_teaser_sections(TEASER_THEN_FAQ.replace("## Handpicked for You", "## Recent News")
                                      .replace("Keep reading", "Read More"))
    assert "Recent News" not in out and "Card one title" not in out


def test_dated_teaser_removed_with_its_more_link_but_faq_kept():
    out, removed = c.remove_teaser_sections(DATED_TEASER_THEN_FAQ)
    assert "Handpicked" not in out and "Card one title" not in out and "Jan 2, 2026" not in out
    assert "cut off" not in out and "Read more money tips" not in out
    assert "Product text that must stay." in out
    assert "## Frequently Asked Questions" in out and "Answer that must stay." in out
    assert len(removed) == 1


def test_bold_links_without_dates_are_not_teasers():
    out, removed = c.remove_teaser_sections(BOLD_FEATURE_LINKS)
    assert out == BOLD_FEATURE_LINKS and removed == []


def test_single_card_like_line_is_not_a_teaser():
    out, removed = c.remove_teaser_sections(STARTUP_COACHING)
    assert out == STARTUP_COACHING and removed == []


def test_popup_removed():
    page = ("Real text.\n\n✕\n\n**Heads up! This link leads to a different website.**\n\n"
            "We only do this when it's helpful for you. But we must inform you that Dupaco isn't responsible for x.\n\n"
            "[Continue](https://www.dupaco.com/x#) Cancel\n")
    out, _ = c.remove_popups(page)
    assert out.split() == ["Real", "text."]


def test_images_removed_links_kept_as_text():
    out, _ = c.strip_images("A ![logo](https://x/y.png) B [![pic](https://x/p.png)](https://x/page) C")
    out, links = c.strip_links(out)
    assert out.split() == ["A", "B", "C"]
    assert links == [Link(text="", url="https://x/page")]
    out, links = c.strip_links("Go to [Become a member](https://join.dupaco.com/) now.")
    assert out == "Go to Become a member now."
    assert links == [Link(text="Become a member", url="https://join.dupaco.com/")]


def test_footnote_link_dropped_not_glued_to_value():
    out, links = c.strip_links("Earn $300 [1](https://x/offer#fine-print) cash, or $300[2](https://x/offer#fine-print).")
    assert out == "Earn $300  cash, or $300."
    assert [link.text for link in links] == ["1", "2"]          # the link itself is still recorded


def test_icon_button_keeps_label_and_url():
    page = ("[![Calculator](https://www.dupaco.com/hubfs/icons/Calculator.svg)\\\\\n\\\\\n"
            "**Calculators**](https://www.dupaco.com/calculators?hsLang=en)\n")
    cleaned = clean_page(page)
    assert cleaned.text == "**Calculators**\n"
    assert cleaned.links == [Link(text="**Calculators**", url="https://www.dupaco.com/calculators?hsLang=en")]


def test_url_with_brackets():
    url = "https://www.dupaco.com/hubfs/Custom-Budget-Worksheet-11(Money%20MakeoverSheet).csv?hsLang=en"
    cleaned = clean_page(f"[**Budget Worksheet**]({url})\n\n![x](https://a/b%20(1).png) after\n")
    assert cleaned.text.split() == ["**Budget", "Worksheet**", "after"]
    assert cleaned.links == [Link(text="**Budget Worksheet**", url=url)]


def test_widgets_country_list_and_form_chrome_removed():
    page = "\n".join(["Keep me", "reCAPTCHA", "Please try again.", "Messenger Launcher",
                      "- \U0001F1E6\U0001F1EB Afghanistan (...) +93", "- \U0001F1FA\U0001F1F8 United States +1",
                      "\U0001F1FA\U0001F1F8", "What time of day works best for your appointment? (Required)\\*",
                      "Submit", "Hint: This form uses a connection that may not be secure. So please don't."])
    out = page
    for rule in (c.remove_widgets, c.remove_country_list, c.remove_form_chrome):
        out, _ = rule(out)
    assert out.strip() == "Keep me"


def test_required_fields_and_carousel_buttons_removed():
    page = "\n".join(["Keep me", "First Name\\*", "**Email**\\*", "Which option suits you?\\*",
                      "Previous", "Next", "- Option kept"]) + "\n"
    out, _ = c.remove_form_chrome(page)
    out, _ = c.remove_widgets(out)
    assert out.split("\n") == ["Keep me", "- Option kept", ""]


def test_captcha_block_removed_but_real_text_and_tables_kept():
    page = "\n".join(["Keep me", "Select all squares with **lanterns** If there are none, click skip", "",
                      "|     |     |", "| --- | --- |", "|  |  |", "|  |  |", "",
                      "|     |     |", "| --- | --- |", "| ![](https://example.com/tile.png) |  |", "", "Verify",
                      "Recaptcha requires verification.", "protected by **reCAPTCHA**", "", "203.0.113.7", "",
                      "Verify the caller before you give out anything.", "", "| Fee | Amount |", "| --- | --- |",
                      "| Example fee | $1.00 |"]) + "\n"
    out, _ = c.remove_widgets(page)
    assert "lanterns" not in out and "|  |  |" not in out and "tile.png" not in out and "\nVerify\n" not in out and "Recaptcha" not in out
    assert "203.0.113.7" not in out
    assert "Keep me" in out and "Verify the caller before you give out anything." in out
    assert "| Example fee | $1.00 |" in out and "| Fee | Amount |" in out


def test_footnote_marked_content_is_not_a_form_label():
    page = "- $0 annual fee\\*\nExample copy fee $1.00\\*\nA question in a sentence? Yes.\n"
    out, removed = c.remove_form_chrome(page)
    assert out == page and removed == []


def test_tables_dates_and_footnotes_untouched():
    page = ("Example Savings\n\n| Account Type | Balance Tier | APY |\n| --- | --- | --- |\n"
            "| Example Savings | $1 - $999.99 | 1.23%4 |\n\nRates are effective as of 01/02/2026.\n")
    text = clean_page(page).text
    assert "| Example Savings | $1 - $999.99 | 1.23%4 |" in text
    assert "Rates are effective as of 01/02/2026." in text


def test_article_header_kept():
    page = ("2 min read\n\n[Some Author](https://www.dupaco.com/newsroom/author/some-author)\n\nJune 18, 2024\n\n"
            "# A News Story\n\nBody.\n\n## Handpicked" + TEASER_THEN_FAQ.split("## Handpicked", 1)[1])
    text = clean_page(page).text
    assert header_date(text) == "June 18, 2024" and "Some Author" in text


def test_formatting():
    out = c.normalize_text(c.normalize_crlf("a\\\\r\\\\nb c‎\n\n\n\n\nd   \n\\# # #\n\n* * *\n"))
    assert out == "a b c\n\nd\n"


def test_listing_pages():
    assert is_listing_page("https://www.dupaco.com/learn/blog/tag/auto")
    assert is_listing_page("https://www.dupaco.com/newsroom/author/someone")
    assert not is_listing_page("https://www.dupaco.com/personal/savings-account")


@pytest.mark.skipif(not (ROOT / "snapshots" / "05_2026-09-28_latest").exists(), reason="snapshots not unpacked")
def test_no_expected_value_lost_outside_teasers():
    """For every public question: a must_include value on a raw page outside teaser sections and images (both
    removed on purpose) is still on the cleaned page, in its text or its saved link URLs."""
    items = [json.loads(line) for line in (ROOT / "eval/public_eval.jsonl").read_text().splitlines() if line.strip()]
    snaps = sorted(d for d in (ROOT / "snapshots").iterdir() if (d / "manifest.json").exists())
    lost = []
    for item in items:
        if not item.get("must_include"):
            continue
        snap = snaps[-1] if not item.get("as_of") else [s for s in snaps if s.name[3:13] <= item["as_of"]][-1]
        for page in json.loads((snap / "manifest.json").read_text())["pages"]:
            if is_listing_page(page["url"]):
                continue
            raw = (snap / page["file"]).read_text()
            visible, _ = c.strip_images(c.remove_teaser_sections(raw)[0])
            cleaned = clean_page(raw)
            kept = cleaned.text + "\n" + " ".join(link.url for link in cleaned.links)
            lost += [(item["id"], tok, page["url"]) for tok in item["must_include"]
                     if contains(visible, tok) and not contains(kept, tok)]
    assert not lost, lost[:20]
