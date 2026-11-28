"""The chronicle of a case: facts as the source of the read models.

- ``facts``: the facts on the path of winning an assignment and their effects.
- ``effects``: what a fact does to the rows, as plain data.
- ``ledger``: the fold of a chronicle into the state at a moment.
- ``writer``: ``establish``, the one way a fact enters the chronicle.
- ``rates``: the rate book as it stood.
- ``verify``: comparing the fold with the rows, and writing it back.
- ``words``: a fact in Dutch, in the form it was established.
- ``guard``: for tests, nothing writes around the chronicle.

The vocabulary comes from chronolexografie. See ADR 0056 and docs/kroniek.md.
"""
