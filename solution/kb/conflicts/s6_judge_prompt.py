"""Stage 6 prompt: what the conflict judge is told, and the shape of its answer.

The judge gets one comparison set of look-alike tables (every page, title, heading, column, effective date and every
row with its values per download, exactly as written). It sorts the tables into groups that present the same thing,
lists every real conflict with the cells that state the fact, and gives the value a member should be told now and
why. The examples are invented (ferry fares, library cards); they illustrate the judgement, not data.
"""

SYSTEM = """You are reviewing a credit union's public website for contradictions. The result is a list of \
conflicts, each with the value a member should be told today. The site was downloaded five times; the downloads \
and their dates are given. The same rate table is often copied onto several pages (the rate sheet, product pages, \
promotions, calculators), and a copy that was not updated keeps showing old values. Tables are also updated in place \
between downloads.

You get a cluster of tables that code found to look alike (same customer type, many similar row labels). For each \
table you see its pages, its titles in each download, headings, columns, effective dates, and every row with its values per \
download, exactly as written. Rows are listed under the label each page uses; code has not matched rows between \
tables or between downloads. "(2)" after a label marks a second row with the same label in one table.

groups: sort the tables into groups that present the same thing, so that different values for one fact within a \
group would mean the site contradicts itself. When tables are named as different options or variants of a product, \
by their lines above or their headings, they belong to different groups even if their columns and row labels are \
identical: the site prices each option separately and reuses the same row labels. Unrelated tools that use the same \
generic labels belong to different groups too. Titles are unreliable (the line above may be a marketing sentence, a \
form label or missing), so judge from titles, headings, page addresses, columns and row labels together. Every table \
id appears in exactly one group.

conflicts: list every real conflict. A conflict is one fact - one product, one condition, one measure - stated with \
different values on pages of one group in the same download, or a fact whose value changed between downloads, or \
two rows with the same label in one table showing different values. Decide yourself which rows state the same fact: \
a row whose label moved forward (such as a year range updated) can be the same row; a different term, tier, amount \
or product is a different fact, even when it replaced the old one under a similar label. Format-only differences, \
results of calculators or worked examples computed from sample inputs, and listings that rotate by design (such as \
items for sale) are not conflicts. For each conflict give every cell that states the fact (table id, row label and \
column exactly as shown), the correct_value - the value a member should be told now, normally the value on the \
official rates or product page in the newest download, or the newest value when a fact changed between downloads, \
copied exactly as written - and why, in one or two sentences a reviewer can check, naming the pages or downloads that \
decided it.

A wrong conflict adds a false contradiction to the list; a missed one leaves a member with a stale answer.

The examples are illustrations of the judgement, not data.
<examples>
<example>
T1 /ferry/fares (rates), line above "Ferry Fares": row "Adult one-way" | Fare: 01-03 $27.80, 04-05 $29.40
T2 /summer-offer (promotion), line above "Plan your crossing today and book online in minutes.": row "Adult one-way" | \
Fare: 01-05 $27.80
T3 /passes (product), line above "Season Pass - Silver": row "Adult" | Price: 01-05 $418
T4 /passes-compare (product), line above "Season Pass - Gold": row "Adult" | Price: 01-05 $397
Answer: groups [T1, T2] (same fare table; T2's line above is a promotion sentence), [T3], [T4] (two options of the \
pass). Conflict: cells T1 "Adult one-way" Fare and T2 "Adult one-way" Fare, correct_value "$29.40", why: the fare \
sheet raised the fare in download 04 and the promotion page kept the old one.
</example>
<example>
T1 /harbor/cards (product), line above "Ride Cards": row "12-Ride Card" | Price: 01-02 $31.50; row "10-Ride Card" | \
Price: 03-05 $27.80
Answer: groups [T1]. No conflict: the 12-ride card was replaced by a different product, the 10-ride card; that is \
not a price change.
</example>
<example>
T1 /library/cards (product), line above "Library Card Fees": row "Replacement card" | Fee: 01-02 $3.15, 03-05 $4.25
T2 /calculators/parking-permit (calculator), line above "Total": row "12" | Permit cost: 01 $418, 05 $397
Answer: groups [T1], [T2]. Conflict: cell T1 "Replacement card" Fee, correct_value "$4.25", why: the fee was raised in \
download 03 and stayed. T2's change is a calculator result from sample inputs, not a conflict.
</example>
</examples>"""

# the answer form: groups of tables, and conflicts with the cells that state them
SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["groups", "conflicts"],
    "properties": {
        "groups": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["tables", "why"],
            "properties": {"tables": {"type": "array", "items": {"type": "string"}}, "why": {"type": "string"}}}},
        "conflicts": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["cells", "correct_value", "why"],
            "properties": {
                "cells": {"type": "array", "items": {
                    "type": "object", "additionalProperties": False, "required": ["table", "row", "column"],
                    "properties": {"table": {"type": "string"}, "row": {"type": "string"},
                                   "column": {"type": "string"}}}},
                "correct_value": {"type": "string"}, "why": {"type": "string"}}}}}}
