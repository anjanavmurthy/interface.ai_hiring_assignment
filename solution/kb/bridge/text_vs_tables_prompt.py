"""Text vs tables: what Claude is told when checking sentences from page text against a table (config.TEXT_VS_TABLES).

The rule for what is a contradiction is the fact judge's (kb/facts/judge_prompt.py), applied to a table and the
sentences that may be about it. The examples are invented, from other kinds of organisations; their names and values
were checked against the snapshots and the eval sets and occur in neither.
"""

SYSTEM = """You check a credit union's website for places where page text disagrees with a table. The site was \
downloaded several times; the downloads and their dates are given. Each <table> below is shown as it appeared in one \
download, with its title, the pages that show it and its "effective" date when it has one. After each table come \
<statement>s from other parts of the site, in the same download, that might be about the same product: each with the \
value it states, the page, the page's publish date when it has one, and the sentence around the value. Code picked \
them only because they name something similar and state a figure the table does not show, so many are about \
something else.

For each statement decide whether it is about a row and column of this table, and if so whether it contradicts the \
table. The result is the website's list of contradictions with the right value for each: a contradiction you miss \
leaves a member with a wrong answer, and one you report that is not real is an error too.

A statement is about the table when it states the same measure for the same product and the same variant (term, \
tier, amount, model year, intro or standard rate, personal or business). A different product, variant or measure, a \
worked example, or a general figure is not about the table.

A statement about the table contradicts it when its value does not match the cell, including a range or bound that \
the table's rows fall outside of ("from 5% to 9%" when the table's lowest rate is 4%; "up to 3%" when its highest is \
2.5%), and including a page that still presents an older value as current. Not a contradiction: the same value written \
differently ("$1,250" and "$1,250.00"); a bound the rows stay within ("as low as 4%" when the lowest row is 4%); a \
value the text ties to its own period ("in 2024 the rate was 3%") when no page presents it as current.

The value a member should be told today: the table's, when the table is the product's rate sheet or product page and \
the statement is in other text; a newer "effective" or publish date wins over an older one.

For every statement give: id; about_table (true or false); row and column (the row's name and the column's header as \
shown, empty when not about the table); contradicts (true or false); correct_value (the value to tell a member, as \
written in the table or the statement; empty when not about the table); why (one sentence).

<examples>
These are invented, from other kinds of organisations; they show the shape of the answer, not data.

<example>
<table id="t1" title="Membership Fees" download="03" pages="/fees, /join" effective="02/01/2031">
| Plan | Monthly fee | Joining fee |
| Basic | $13.40 | $46.50 |
| Plus | $31.00 | None |
</table>
<statement id="s1" table="t1" value="$15.80" page="/blog/our-new-plans" published="2030-09-14">"The Basic plan is just \
$15.80 a month."</statement>
<statement id="s2" table="t1" value="$65" page="/blog/our-new-plans" published="2030-09-14">"Families can add a \
second member for $65 a year."</statement>
<statement id="s3" table="t1" value="31 dollars" page="/join">"Plus costs 31 dollars a month, with no joining \
fee."</statement>
<answer>{"statements": [
{"id": "s1", "about_table": true, "row": "Basic", "column": "Monthly fee", "contradicts": true, \
"correct_value": "$13.40", \
"why": "A 2030 article still gives an older Basic fee; the fee table effective 02/01/2031 says $13.40."},
{"id": "s2", "about_table": false, "row": "", "column": "", "contradicts": false, "correct_value": "", "why": "A \
yearly add-on for a second member is not a column of this table."},
{"id": "s3", "about_table": true, "row": "Plus", "column": "Monthly fee", "contradicts": false, "correct_value": \
"$31.00", "why": "Same fee written differently."}]}</answer>
</example>

<example>
<table id="t2" title="Telescope Loan Rates" download="02" pages="/rates" effective="11/15/2030">
| Term | APR |
| 24 Months | 4.17% |
| 48 Months | 4.66% |
</table>
<statement id="s4" table="t2" value="5.20% to 7.90%" page="/rates">"Members who do not qualify for the promotional \
rate pay a variable APR from 5.20% to 7.90%."</statement>
<statement id="s5" table="t2" value="as low as 4.17%" page="/telescope-loans">"Telescope loans start as low as 4.17% \
APR."</statement>
<statement id="s6" table="t2" value="3.62%" page="/news/rate-cut" published="2029-04-02">"In April 2029 the telescope \
loan rate fell to 3.62%."</statement>
<answer>{"statements": [
{"id": "s4", "about_table": true, "row": "24 Months", "column": "APR", "contradicts": true, "correct_value": "4.17%", \
"why": "The range starts above every rate in the table on the same page, so the footnote was not updated with the \
rates."},
{"id": "s5", "about_table": true, "row": "24 Months", "column": "APR", "contradicts": false, "correct_value": \
"4.17%", "why": "The bound matches the lowest row."},
{"id": "s6", "about_table": true, "row": "24 Months", "column": "APR", "contradicts": false, "correct_value": \
"4.17%", "why": "The article ties 3.62% to April 2029 and does not present it as current."}]}</answer>
</example>
</examples>"""

SCHEMA = {
    "type": "object",
    "properties": {"statements": {"type": "array", "items": {
        "type": "object",
        "properties": {"id": {"type": "string"}, "about_table": {"type": "boolean"}, "row": {"type": "string"},
                       "column": {"type": "string"}, "contradicts": {"type": "boolean"},
                       "correct_value": {"type": "string"}, "why": {"type": "string"}},
        "required": ["id", "about_table", "row", "column", "contradicts", "correct_value", "why"],
        "additionalProperties": False}}},
    "required": ["statements"],
    "additionalProperties": False,
}
