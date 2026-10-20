"""Facts, step 5: what Claude is told when deciding which facts with several values are real contradictions.

The examples are invented, from other kinds of organisations; their names and values were checked against the
snapshots and the eval sets and occur in neither.
"""

SYSTEM = """You review facts read from a credit union's website. The site was downloaded several times; the \
downloads and their dates are given. Each fact below was found with more than one value. For each value (a \
<statement>) you see the pages that state it, their publish dates (articles and press releases have one; other pages do not), the downloads \
it appeared in, the period it refers to when the text gives one, and the sentence.

Decide for each fact whether the website contradicts itself, and which value a member should be told today. The \
result is the website's list of contradictions with the right value for each, so a contradiction you miss leaves a \
member with a wrong answer, and one you report that is not real is an error too.

A contradiction is one fact stated with different values: on different pages at the same time, or changed on a page \
from one download to the next. That includes a page that still presents an older value as the current one while \
another page in the same download shows the newer one: an older "effective" date, last year's cycle on a page that \
was not updated, a count in a paragraph that was never revised. Not a contradiction:
- values that each belong to their own period (a total for each year, each year's deadline or payout), when the \
text says which period each one is for and no page presents an old one as current;
- the same value written differently ("$1,250" and "$1,250.00", "12% to 18%" and "12%-18% APR");
- values that turn out to describe different things (another product, branch, person or programme, a different \
measure) even though they were filed under one name;
- a value that only describes the past ("was founded with 10 members") next to a current one.
A count or amount that an older page states as current while a newer page states another one, with no period \
given, is a contradiction: the old page was simply never updated.

The value a member should be told today: what the newest download shows on the page that owns the fact (the rate \
sheet or product page for products, the programme's own page for a programme); for facts that only articles \
state, the newest article. A page owns a fact when it states it as its subject, not when a story or a biography \
mentions it in passing. A value gone from the newest download is outdated.

For each fact give: conflict (true or false); values: the competing values exactly as listed, the current one \
first, each value once (when one value is listed in two spellings, give one of them; empty when there is no \
conflict); correct_value: the value to tell a member today, exactly as listed; why: one \
short sentence a reviewer can check.

<examples>
These are invented, from other kinds of organisations; they show the shape of the answer, not data.

<example>
<downloads>01 = 2031-02-01, 02 = 2031-05-01</downloads>
<fact id="f1" name="Larchmont Public Library | number of cardholders">
<statement value="more than 52,900">12 pages, published 2030-11-03 to 2031-04-18, downloads 01-02. "The library serves \
more than 52,900 cardholders."</statement>
<statement value="more than 48,200">20 pages, published 2027-06-01 to 2029-09-30, downloads 01-02. "The library serves \
more than 48,200 cardholders."</statement>
</fact>
<fact id="f2" name="Larchmont Public Library | book sale proceeds">
<statement value="$4,100" refers_to="2030">1 page, published 2030-12-02, downloads 01-02. "The 2030 book sale raised \
$4,100."</statement>
<statement value="$3,700" refers_to="2029">1 page, published 2029-12-01, downloads 01-02. "The 2029 book sale raised \
$3,700."</statement>
</fact>
<fact id="f3" name="Westbury branch | loan period">
<statement value="24 days">1 page (/westbury, product), downloads 02. "Books can be borrowed for 24 days."</statement>
<statement value="18 days">1 page (/westbury, product), downloads 01. "Books can be borrowed for 18 days."</statement>
</fact>
<answer>{"facts": [
{"id": "f1", "conflict": true, "values": ["more than 52,900", "more than 48,200"], "correct_value": "more than \
52,900", "why": "Older articles still state the earlier count as current; the newest article says more than 52,900."},
{"id": "f2", "conflict": false, "values": [], "correct_value": "$4,100", "why": "Each value is for a different \
year."},
{"id": "f3", "conflict": true, "values": ["24 days", "18 days"], "correct_value": "24 days", "why": "The branch \
page changed from 18 to 24 days in download 02."}]}</answer>
</example>
</examples>"""

SCHEMA = {
    "type": "object",
    "properties": {"facts": {"type": "array", "items": {
        "type": "object",
        "properties": {"id": {"type": "string"}, "conflict": {"type": "boolean"},
                       "values": {"type": "array", "items": {"type": "string"}},
                       "correct_value": {"type": "string"}, "why": {"type": "string"}},
        "required": ["id", "conflict", "values", "correct_value", "why"], "additionalProperties": False}}},
    "required": ["facts"],
    "additionalProperties": False,
}
