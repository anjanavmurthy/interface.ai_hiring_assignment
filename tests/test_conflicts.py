"""Tests for kb.conflicts stage 4: rows are read only through the column roles of stage 3."""
from kb.conflicts.s1_read_tables import cells, outline_page
from kb.conflicts.s4_track_tables import read_versions, row_name
from kb.conflicts.table_text import header_key

TIERS = """## Example Rates

| Account | Balance Tier | APY |
| --- | --- | --- |
| Example Club | $9,000+ | 0.31% |
| Example Club | $1 - $8,999.99 | 0.12% |
"""
TIER_ROLES = {header_key(cells("| Account | Balance Tier | APY |")): ["product", "condition", "value"]}


def versions(text: str, roles: dict) -> list[dict]:
    return read_versions([outline_page("01", "https://www.dupaco.com/example", text)], roles)[1]


def test_tiers_keep_separate_names():
    (v,) = versions(TIERS, TIER_ROLES)
    assert v["names"] == ["Example Club | $9,000+", "Example Club | $1 - $8,999.99"]
    assert v["value_cols"] == [2]


def test_table_without_roles_or_values_is_skipped():
    assert versions(TIERS, {}) == []
    no_values = {header_key(cells("| Account | Balance Tier | APY |")): ["product", "condition", "ignore"]}
    assert versions(TIERS, no_values) == []


def test_transposed_table_is_named_by_its_measure_label():
    roles = ["measure label", "value", "value"]
    assert row_name(["Minimum to open", "$10", "$20"], roles) == "Minimum to open"
    assert row_name(["", "$10", "$20"], roles) == ""
