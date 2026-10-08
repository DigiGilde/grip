"""The link with Wies, the system that shows who works where.

Wies is the source of people; grip is the source of placements. Both belong
to the same organisation, so this is a machine interface with a key and not
federated traffic (see docs/wies.md and ADR 0013).

- ``export``: what Wies pulls from grip: assignments, roles, placements and
  open roles. Data classes A and C only.
- ``client``: reads colleagues from Wies.
- ``reconcile``: compares those colleagues with grip's persons and proposes
  additions and deactivations for the beheerder to confirm.
"""
