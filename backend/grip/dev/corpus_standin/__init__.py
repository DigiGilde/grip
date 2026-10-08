"""A stand-in corpus system for local development.

Serves corpus-context v1 as the contract defines it, from the fictional
corpus in ``corpus.json``. It plays outway and corpus at once: the dev
backend sets ``OUTWAY_URL`` to this app and reaches each corpus through the
grant hash of the peer, the way a real outway routes on the contract.
"""

from grip.dev.corpus_standin.data import (
    Corpus,
    corpora,
    corpus_by_key,
    node_uri,
)

__all__ = ["Corpus", "corpora", "corpus_by_key", "node_uri"]
