"""Tests for the second pass over page text (kb.facts.wider) and text vs tables (kb.bridge): which paragraphs are
picked, which known names are used, and that a sentence disagreeing with a table row comes out as one conflict. All
values are invented."""
import re

import numpy as np

from kb.bridge.text_vs_tables import text_vs_tables
from kb.conflicts.tracker import TableTracker
from kb.facts.collect import Paragraph
from kb.facts.extract import Fact
from kb.facts.wider import Names, usable, worth_reading

RATES = "https://www.dupaco.com/rates"
PROMO_TEXT = "https://www.dupaco.com/learn/blog/example-post"
TABLE_PAGE = "\n\n".join([
    "# Example Saver rates",
    "Rates are effective as of 01/02/2030.",
    "| Product | Term | APY |\n|---|---|---|\n"
    "| Example Saver | 6 Month | 1.10% |\n| Example Saver | 12 Month | 1.30% |",
])


class FakeLLM:
    """Answers like the stages expect: s3 labels (product, condition, value); for text vs tables, every statement is
    about the first row's APY and contradicts it. Records the statements it was sent."""

    def __init__(self):
        self.sent = []

    def ask(self, system, user, schema):
        props = schema["properties"]
        if "layouts" in props:
            ids = re.findall(r'<layout id="([^"]+)">', user)
            cols = [{"index": 0, "header": "Product", "role": "product", "name": "product"},
                    {"index": 1, "header": "Term", "role": "condition", "name": "term"},
                    {"index": 2, "header": "APY", "role": "value", "name": "APY"}]
            return {"layouts": [{"id": i, "kind": "offer table", "transposed": False, "product_source": "column",
                                 "note": "", "columns": cols} for i in ids]}
        ids = re.findall(r'<statement id="([^"]+)"', user)
        self.sent += re.findall(r'<statement id="[^"]+" table="[^"]+" value="([^"]*)"', user)
        return {"statements": [{"id": i, "about_table": True, "row": "6 Month", "column": "APY", "contradicts": True,
                                "correct_value": "1.10%", "why": "test"} for i in ids]}


class SameEmbedder:
    """Every text equally close: the shortlist is decided by the figures alone."""

    def embed(self, texts):
        return np.ones((len(texts), 4)) / 2


def test_new_rules_skip_bylines_quotes_and_bare_numbers():
    assert worth_reading("Applications are accepted from March 3 to April 9, 2030 at any branch.")
    assert worth_reading("We added two new ways to pay your loan this spring.")
    assert not worth_reading("Example Author\nMarch 04, 2030")                       # a byline
    assert not worth_reading('"We loved it," said the member who joined last year.')  # a quotation
    assert not worth_reading("Step 2 is to list the twelve things you want to save for.")


def test_known_names_are_capitalised_and_not_too_common():
    paragraphs = [f"Advice paragraph {i} about a checking account." for i in range(100)] + ["Open an Example Saver."]
    names = usable({"Example Saver", "checking account", "Advice", "Ex"}, paragraphs)
    assert names == {"Example Saver"}                     # lowercase phrase, too common, too short: dropped
    assert Names(names).found_in("Open an Example Saver today.") == {"Example Saver"}
    assert Names(names).found_in("an example saver") == set()          # matched with its case


def test_sentence_disagreeing_with_a_table_is_one_conflict_and_matching_ones_are_not_sent():
    tracker = TableTracker(FakeLLM())
    tracker.add_snapshot("01_2030-01-10_test", [(RATES, TABLE_PAGE)])
    para = Paragraph("p1", "Earn up to 1.50% APY with an Example Saver.", {PROMO_TEXT: {"01"}}, {})
    same = Paragraph("p2", "Lock in 1.30% APY for 12 months.", {PROMO_TEXT: {"01"}}, {})
    differs = Fact(para, "Example Saver", "product", "up to APY", "up to 1.50%", "")
    repeats = Fact(same, "Example Saver", "product", "APY", "1.30%", "")
    judge = FakeLLM()
    found = text_vs_tables([differs, repeats], tracker, [], SameEmbedder(), judge, {"01": "2030-01-10"})
    assert judge.sent == ["up to 1.50%"]                    # a sentence repeating the table's figure is not sent
    assert len(found) == 1 and set(found[0].values) == {"1.10%", "up to 1.50%"} and found[0].correct_value == "1.10%"
    assert {f.origin for fs in found[0].values.values() for f in fs} == {"text", "table"}
