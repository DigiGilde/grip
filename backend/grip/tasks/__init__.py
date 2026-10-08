"""Tasks: facts from the domain, work for people, and a plan between them.

- ``catalogue``: the subjects, facts, roles and anchors a plan may name.
- ``plan``: the plan as data, checked against the catalogue.
- ``cases``: the facts of a case, read from the domain tables.
- ``engine``: brings the tasks of a case in line with its facts.
- ``service`` and ``access``: what a person sees and does with tasks.

See ADR 0024 and docs/taken.md.
"""
