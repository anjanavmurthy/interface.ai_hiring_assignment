"""Tests for kb.history and kb.changes: what the answer sees as of a download, and when older values appear at all."""
from kb.changes import ChangeLog
from kb.history import Record, record_line, refers_to_another_time, spans

FACT = Record(text="", kind="fact", name="Example Club | members",
              seen=[("01", "40", ("40", ""), "2030-01-01"), ("02", "40", ("40", ""), "2030-01-01"),
                    ("03", "45", ("45", ""), "2030-03-01"), ("04", "45", ("45", ""), "2030-03-01")])
GONE = Record(text="", kind="fact", name="Example card | intro rate",
              seen=[("01", "0.99%", ("0.99%", ""), ""), ("02", "0.99%", ("0.99%", ""), "")])
PAGE = "https://www.dupaco.com/example-rates"


def test_download_spans():
    assert spans(["01", "02", "03", "05"]) == "01-03, 05" and spans(["04"]) == "04"


def test_question_about_now_sees_only_what_is_shown_now():
    assert record_line(FACT, "04", False, {}) == ("Example Club | members: shown now: 45 (downloads 03-04, "
                                                  "published 2030-03-01)")
    assert record_line(GONE, "04", False, {}) == "Example card | intro rate: no longer shown (last seen in download 02)"


def test_question_about_another_time_sees_earlier_values_but_never_later_ones():
    assert "earlier, no longer shown: 40 (downloads 01-02" in record_line(FACT, "04", True, {})
    assert "45" not in record_line(FACT, "02", True, {})
    assert record_line(FACT, "00", True, {}) is None


def test_time_references_and_years_that_name_a_product():
    assert refers_to_another_time("What did it pay before the change?", None)
    assert refers_to_another_time("What was the rate in March 2030?", None)
    assert refers_to_another_time("What is the rate as of 2030?", None)
    assert refers_to_another_time("What is the rate?", "2030-03-01")
    assert not refers_to_another_time("What is the current rate?", None)
    assert not refers_to_another_time("What APR for a 2029 model-year car?", None)     # a year that names the product


def test_changes_index_keeps_before_and_after_up_to_the_answered_download():
    log = ChangeLog()
    log.add_snapshot("01_2030-01-01_t", [(PAGE, "## Example Club\n\nThe example fund pays 1.10%.\n\nOther text.")])
    log.add_snapshot("02_2030-02-01_t", [(PAGE, "## Example Club\n\nThe example fund pays 1.20%.\n\nOther text.")])
    text = log.lines("example fund", "02")
    assert "download 01 -> 02" in text
    assert "before: The example fund pays 1.10%." in text and "after: The example fund pays 1.20%." in text
    assert log.lines("example fund", "01") == ""
