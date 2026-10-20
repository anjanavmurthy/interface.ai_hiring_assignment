"""Stage 3 prompt: what the column-labelling LLM is told, and the shape of its answer.

The LLM sees one table layout at a time (its header row, the titles it appears under, page types and a few example
rows) and says what kind of table it is and the role of every column: product, condition, value, measure label or
ignore. The examples are invented, from other kinds of websites; their values and names were checked against the
snapshots and the eval files so none occur there.
"""

LAYOUT_SYSTEM = """You are helping turn the tables of a credit union's website into separate facts, so the same fact
can be compared across pages and across five downloads of the site. Code will read every row of every table; you
are shown one kind of table at a time (a layout: its header row, the titles it appears under, the page types, and a
few example rows) and say once how its columns should be read.

For each layout say what kind of table it is: an "offer table" states the credit union's own rates, fees, terms,
limits or requirements; a "listing" lists items such as vehicles for sale or events; a "form or worksheet" has
fields to fill in or a budget to complete; a "calculation example" shows sample payments or balances worked out for
an illustration; "other" is anything else.

Then give each column a role. A "product" column names what the row is about (an account, card, loan or plan). A
"condition" column says which variant of it the row is for: a term, balance tier, loan amount, model year or similar.
A "value" column holds what the site states about that variant and could change: a rate, APY, APR, fee, minimum,
payment or limit. Use "ignore" for empty or decorative columns. When no column names the product, say whether the
product comes from the table's title or its section heading. A table is "transposed" when its column headers name the
variants (for example plan names) and each row is one measure; then the first column has the role "measure label"
and the other columns are "value" columns whose header names the variant.

Name each condition and value column with a short standard name, so the same measure gets the same name in every
layout: for values use names such as APY, dividend rate, APR, interest rate, points, payment example, minimum to
open, minimum to earn, minimum balance, fee, credit limit; for conditions use names such as term, balance tier, loan
amount, model year. Column positions start at 0 with the first column. The examples below are made up, from other
kinds of websites; they show the shape of the answer, not data."""

LAYOUT_EXAMPLES = """<examples>
<example>
<layout id="X1">
Header: | Plan | Monthly Fee (US$)2 | Joining Fee | Visits per Month |
Titles: "Membership Plans"; "Our Plans"
Page types: product
Example rows:
| Off-peak | $27.80 | $17 | 8 |
| Family | $63.10 | $17 | Unlimited |
</layout>
<answer>{"id": "X1", "kind": "offer table", "transposed": false, "product_source": "column", "note": "",
 "columns": [{"index": 0, "header": "Plan", "role": "product", "name": "plan"},
             {"index": 1, "header": "Monthly Fee (US$)2", "role": "value", "name": "monthly fee"},
             {"index": 2, "header": "Joining Fee", "role": "value", "name": "joining fee"},
             {"index": 3, "header": "Visits per Month", "role": "value", "name": "visits per month"}]}</answer>
</example>
<example>
<layout id="X2">
Header: | Distance | Standard Fare | Express Fare |
Titles: "Ferry Passes"
Page types: product
Example rows:
| Up to 5 miles | $3.15 | $4.65 |
| 5 to 12 miles | $5.25 | $6.95 |
</layout>
<answer>{"id": "X2", "kind": "offer table", "transposed": false, "product_source": "title", "note": "",
 "columns": [{"index": 0, "header": "Distance", "role": "condition", "name": "distance"},
             {"index": 1, "header": "Standard Fare", "role": "value", "name": "standard fare"},
             {"index": 2, "header": "Express Fare", "role": "value", "name": "express fare"}]}</answer>
</example>
<example>
<layout id="X3">
Header: |  | Basic Card | Premium Card |
Titles: "Compare Library Cards"
Page types: product
Example rows:
| Late fee per day | $0.35 | None |
| Items per loan | 12 | 30 |
</layout>
<answer>{"id": "X3", "kind": "offer table", "transposed": true, "product_source": "title", "note": "columns are card types",
 "columns": [{"index": 0, "header": "", "role": "measure label", "name": "measure"},
             {"index": 1, "header": "Basic Card", "role": "value", "name": "Basic Card"},
             {"index": 2, "header": "Premium Card", "role": "value", "name": "Premium Card"}]}</answer>
</example>
<example>
<layout id="X4">
Header: | Applicant Name | Date of Birth | Signature |
Titles: "Club Membership Application"
Page types: pdf
Example rows:
| | | |
</layout>
<answer>{"id": "X4", "kind": "form or worksheet", "transposed": false, "product_source": "title", "note": "blank form fields",
 "columns": [{"index": 0, "header": "Applicant Name", "role": "ignore", "name": ""},
             {"index": 1, "header": "Date of Birth", "role": "ignore", "name": ""},
             {"index": 2, "header": "Signature", "role": "ignore", "name": ""}]}</answer>
</example>
</examples>"""

# the answer form: one entry per layout, one role per column
COLUMN = {"type": "object", "additionalProperties": False, "required": ["index", "header", "role", "name"],
          "properties": {"index": {"type": "integer"}, "header": {"type": "string"},
                         "role": {"type": "string", "enum": ["product", "condition", "value", "measure label", "ignore"]},
                         "name": {"type": "string"}}}
LAYOUT_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["layouts"], "properties": {"layouts": {
    "type": "array", "items": {"type": "object", "additionalProperties": False,
                               "required": ["id", "kind", "transposed", "product_source", "note", "columns"],
                               "properties": {"id": {"type": "string"},
                                              "kind": {"type": "string", "enum": ["offer table", "listing",
                                                       "form or worksheet", "calculation example", "other"]},
                                              "transposed": {"type": "boolean"},
                                              "product_source": {"type": "string", "enum": ["column", "title", "section"]},
                                              "note": {"type": "string"},
                                              "columns": {"type": "array", "items": COLUMN}}}}}}

SYSTEM = LAYOUT_SYSTEM + "\n\n" + LAYOUT_EXAMPLES      # what is sent as the system prompt
