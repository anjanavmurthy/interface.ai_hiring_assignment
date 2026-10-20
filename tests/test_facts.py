"""Tests for kb.facts: what is sent to Claude per snapshot, and which extracted values are kept."""
from kb.facts.collect import Collector
from kb.facts.extract import grounded, pack, render

NEWS = "https://www.dupaco.com/newsroom/example-release"
BLOG = "https://www.dupaco.com/learn/blog/example-post"
FOOTER_A = ("Dupaco Community Credit Union is a not-for-profit, member-owned financial cooperative. "
            "It has over 600 employees and 30 branch office locations.")
FOOTER_B = FOOTER_A.replace("30 branch", "31 branch")


def article(*paragraphs: str) -> str:
    return "\n\n".join(["2 min read", "Example Author\nJanuary 05, 2030", "# Example release", *paragraphs])


def sent(docs) -> list[str]:
    return [t for d in docs for t, p in d.parts if p]


def test_page_sent_whole_once_then_only_changes_with_their_section():
    c = Collector()
    first = c.add_snapshot("01_2030-01-10_test", [(NEWS, article("The example fund awards up to $9.", "Second part."))])
    assert "The example fund awards up to $9." in sent(first) and first[0].article_date == "January 05, 2030"
    assert c.add_snapshot("02_2030-02-10_test", [(NEWS, article("The example fund awards up to $9.", "Second part."))]) == []
    third = c.add_snapshot("03_2030-03-10_test", [(NEWS, article("The example fund awards up to $12.", "Second part."))])
    assert sent(third) == ["The example fund awards up to $12."]
    assert "Second part." in [t for d in third for t, p in d.parts if p is None]       # same section, as context
    assert c.paragraphs["Second part."].seen[NEWS] == {"01", "02", "03"}


def test_footer_wordings_sent_once_from_any_page():
    c = Collector()
    docs = c.add_snapshot("01_2030-01-10_test", [(NEWS, article("Body.", FOOTER_A)), (BLOG, article("Advice.", FOOTER_A))])
    assert sent([d for d in docs if d.url == "footer"]) == [FOOTER_A]
    assert "Advice." not in sent(docs)                       # blog pages only contribute their footer copy
    assert set(c.paragraphs[FOOTER_A].seen) == {NEWS, BLOG}
    docs = c.add_snapshot("02_2030-02-10_test", [(NEWS, article("Body.", FOOTER_B))])
    assert sent(docs) == [FOOTER_B]


def test_numbers_must_be_in_the_paragraph_words_may_be_rephrased():
    text = "The fund’s grants reach up to $3,500 and it was renamed."
    assert grounded("up to $3,500", text)
    assert grounded("renamed", text) and grounded("new name adopted", text)
    assert not grounded("$3,600", text) and not grounded(" ", text)
    assert grounded("fund's grants", text)                   # curly vs straight apostrophe


def test_requests_are_packed_up_to_the_limit():
    c = Collector()
    docs = c.add_snapshot("01_2030-01-10_test", [(f"{NEWS}-{k}", article(f"Paragraph {k} " * 20)) for k in range(6)])
    size = len(render(docs[0]))
    groups = pack(docs, 2 * size + 10)
    assert [len(g) for g in groups] == [2, 2, 2]


def test_other_pages_send_only_paragraphs_that_may_state_a_fact_with_context():
    c = Collector()
    text = article("## Saving tips", "Put a little aside each week.", "Dupaco members can open the example account "
                   "with $7.", "Call 555-010-0199, ext. 42 for help.", "| Term | APY |\n| --- | --- |\n| 7 Month | 1.11% |")
    docs = c.add_snapshot("01_2030-01-10_test", [(BLOG, text)])
    assert sent(docs) == ["Dupaco members can open the example account with $7.", "Call 555-010-0199, ext. 42 for help."]
    context = [t for d in docs for t, p in d.parts if p is None]
    assert "## Saving tips" in context and "Put a little aside each week." in context
    assert not any(t.startswith("|") for d in docs for t, _ in d.parts)            # tables: the table stages read them


def test_history_note_gives_the_current_value_first_and_nothing_from_later_downloads():
    from kb.facts.collect import Paragraph
    from kb.facts.extract import Fact
    from kb.facts.judge import Verdict
    from kb.facts.notes import line

    def fact(value, snaps, date):
        p = Paragraph("p1", f"The example club has {value} members.", {NEWS: set(snaps)}, {NEWS: date})
        return Fact(p, "Example Club", "organisation", "members", value, "", "Example Club | members")

    v = Verdict("Example Club | members", {"40": [fact("40", {"01", "02"}, "January 05, 2030")],
                                           "35": [fact("35", {"01"}, "January 05, 2029")]}, "40", "newer article")
    assert line(v, "02").startswith("Example Club | members: 40 is current (published 2030-01-05, last seen in download 02)")
    assert "35 (published 2029-01-05, last seen in download 01)" in line(v, "02")
    assert "download 02" not in line(v, "01")
