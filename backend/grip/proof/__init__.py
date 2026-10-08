"""Proof of a decision: evidence that can be checked outside grip.

When someone accepts or rejects a quote, or approves it internally or sends
it back, grip records more than a row saying so. It asks the identity
provider to authenticate the person again for exactly this act, keeps the
token the provider signed, and writes one statement of the decision that
this instance signs. Together with the quote and the keys they form a
bundle: a file both parties keep and anyone can check with
``python -m grip.proof.verify``, without access to grip or its database.

- ``jose``: reading and verifying compact JWS, standard library and
  ``cryptography`` only.
- ``nonce``: the value that ties an authentication to one decision.
- ``statement``: the statement of a decision, canonical and signed.
- ``idtoken``: what an ID token proves about an authentication.
- ``bundle``: the bundle and the page a person can read.
- ``verify``: checking a bundle, as a library and as a command.
- ``timestamp``: an optional trusted time from a time-stamping authority.

``jose``, ``nonce``, ``idtoken`` and ``verify`` import nothing else from
grip, so the check does not depend on the application that made the bundle.
"""
