"""Tests for kb.conflicts.tracker: tables read per snapshot, only new layouts sent to the LLM, failures isolated."""
import re

from kb.conflicts.s1_read_tables import cells
from kb.conflicts.table_text import header_key
from kb.conflicts.tracker import TableTracker

URL = "https://www.dupaco.com/example-rates"
FEES = "| Service | Fee |"
TERMS = "| Term | APY |"


def page(header: str, rows: list[str]) -> str:
    n = len(cells(header))
    return "\n".join(["## Example", "", header, "|" + " --- |" * n] + rows) + "\n"


class FakeLLM:
    """Answers every layout as an offer table whose first column names the row and the rest are values."""
    def __init__(self, fail: bool = False):
        self.requests, self.fail = [], fail

    def ask(self, system, user, schema):
        self.requests.append(user)
        if self.fail:
            raise RuntimeError("service unavailable")
        layouts = []
        for lid, header in re.findall(r'<layout id="(\w+)">\nHeader: (.*)', user):
            n = len(cells(header))
            layouts.append({"id": lid, "kind": "offer table", "transposed": False, "product_source": "column",
                            "note": "", "columns": [{"index": j, "header": "", "role": "condition" if j == 0 else
                                                     "value", "name": ""} for j in range(n)]})
        return {"layouts": layouts}


def test_only_new_layouts_are_sent():
    llm = FakeLLM()
    t = TableTracker(llm)
    t.add_snapshot("01_2030-01-01_test", [(URL, page(TERMS, ["| 7 Month | 1.11% |"]))])
    assert len(llm.requests) == 1
    t.add_snapshot("02_2030-02-01_test", [(URL, page(TERMS, ["| 7 Month | 1.22% |"]))])
    assert len(llm.requests) == 1                                      # same header: nothing new to label
    t.add_snapshot("03_2030-03-01_test", [(URL, page(TERMS, ["| 7 Month | 1.22% |"])
                                           + "\n" + page(FEES, ["| Example service | $1.00 |"]))])
    assert len(llm.requests) == 2 and "Example service" in llm.requests[-1] and "7 Month" not in llm.requests[-1]
    assert t.roles_of()[header_key(cells(TERMS))] == ["condition", "value"]
    assert [p["snap"] for p in t.pages] == ["01", "02", "03"] and t.snap_dates["02"] == "2030-02-01"


def test_failed_request_leaves_layout_unlabelled_and_is_retried():
    t = TableTracker(FakeLLM(fail=True))
    t.add_snapshot("01_2030-01-01_test", [(URL, page(TERMS, ["| 7 Month | 1.11% |"]))])
    assert t.roles_of() == {}                                          # ingest goes on; the table is just not read
    t.llm = FakeLLM()
    t.add_snapshot("02_2030-02-01_test", [(URL, page(TERMS, ["| 7 Month | 1.11% |"]))])
    assert header_key(cells(TERMS)) in t.roles_of()


def test_untracked_kinds_are_not_read():
    llm = FakeLLM()
    t = TableTracker(llm)
    t.add_snapshot("01_2030-01-01_test", [(URL, page(TERMS, ["| 7 Month | 1.11% |"]))])
    next(iter(t.labels.values()))["kind"] = "calculation example"
    assert t.roles_of() == {}
