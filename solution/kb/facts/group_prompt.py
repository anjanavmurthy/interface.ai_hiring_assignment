"""Facts, step 3: what Claude is told when naming the fact each extracted subject | attribute pair states.

The examples are invented, from other kinds of organisations; their names and values were checked against the
snapshots and the eval sets and occur in neither.
"""

SYSTEM = """Facts were read from a credit union's website, page by page, and each was written down as a subject | \
attribute pair with its value. Different pages describe the same fact in different words. You get the new pairs, \
each with an example value, and the names of the facts already known. Give every new pair the name of the fact it \
states.

Why it matters: the values of one fact are compared across pages and over time, to find the newest value and the \
places where the website contradicts itself. Two different facts under one name create contradictions that do not \
exist; one fact under two names hides real ones. When you are not sure two pairs state the same fact, keep them \
apart.

The same fact: the same subject, even when its name is written differently, shortened or has the organisation's \
name added, and the same measure in other words ("number of members" and "membership"). Different facts: another \
subject (another branch, product, programme or person; the business version of a personal product), or another \
measure (the hours of two different services, weekday and weekend hours, minimum to open and minimum to earn, a \
rate and an APY, a maximum and a typical amount). Values for different years still belong to one fact; the year \
is kept with each value.

Name a fact "subject | attribute" in plain words. When a pair states a fact that is already known, use that name \
exactly. Every new pair gets exactly one name.

<examples>
These are invented, from other kinds of organisations; they show the shape of the answer, not data.

<example>
<known>Larchmont Public Library | number of branch libraries</known>
<new id="n1">Larchmont Library | branches (e.g. "15")</new>
<new id="n2">Larchmont Public Library | cardholders (e.g. "more than 63,800")</new>
<new id="n3">Larchmont Public Library system | number of cardholders (e.g. "61,500")</new>
<new id="n4">Westbury branch | Sunday hours (e.g. "11 a.m.-3 p.m.")</new>
<new id="n5">Westbury branch | Sunday reading-room hours (e.g. "1-3 p.m.")</new>
<new id="n6">Ridgeline Book Club | annual dues (e.g. "$85")</new>
<new id="n7">Ridgeline Book Club for businesses | annual dues (e.g. "$120")</new>
<answer>{"names": [
{"id": "n1", "name": "Larchmont Public Library | number of branch libraries"},
{"id": "n2", "name": "Larchmont Public Library | number of cardholders"},
{"id": "n3", "name": "Larchmont Public Library | number of cardholders"},
{"id": "n4", "name": "Westbury branch | Sunday opening hours"},
{"id": "n5", "name": "Westbury branch | Sunday reading-room hours"},
{"id": "n6", "name": "Ridgeline Book Club | annual dues"},
{"id": "n7", "name": "Ridgeline Book Club for businesses | annual dues"}]}</answer>
</example>
</examples>"""

SCHEMA = {
    "type": "object",
    "properties": {"names": {"type": "array", "items": {
        "type": "object",
        "properties": {"id": {"type": "string"}, "name": {"type": "string"}},
        "required": ["id", "name"], "additionalProperties": False}}},
    "required": ["names"],
    "additionalProperties": False,
}
