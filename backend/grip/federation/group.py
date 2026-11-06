"""The boundary between example instances and real work (ADR 0054).

Example instances federate only with each other, in an FSC group of their
own. Two checks keep that so, independent of each other:

- the peer registry: every peer is marked as example or not. An example
  instance only sends to and accepts from peers marked as example; an
  instance for real work never does. The outway client checks every call
  out, the listener's peer dependency every call in.
- the FSC group itself: an example instance accepts a call only when the
  access token the inway passes on was issued in its own group
  (``EXAMPLE_FSC_GROUP``). A wrong row in the registry is then not enough
  to let a call from another group in.
"""

from __future__ import annotations

import base64
import binascii
import json

from grip.core.config import Settings
from grip.federation.models import Peer

# The header in which the inway passes on the access token of the call.
FSC_AUTHORIZATION_HEADER = "Fsc-Authorization"
# The claim of an FSC access token that names the group it was issued in.
GROUP_CLAIM = "gid"


def same_side(peer: Peer, settings: Settings) -> bool:
    """Whether this instance may exchange anything with this peer."""
    return bool(peer.is_example) == settings.is_example


def token_group(header_value: str) -> str | None:
    """The group id in the access token the inway passed on, if readable.

    The signature is not checked here: the inway did that before passing
    the call on, which is the same trust the peer id header rests on.
    """
    token = header_value.strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    parts = token.split(".")
    if len(parts) != 3:
        return None
    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        claims = json.loads(base64.urlsafe_b64decode(payload))
    except (binascii.Error, ValueError):
        return None
    group = claims.get(GROUP_CLAIM) if isinstance(claims, dict) else None
    return group if isinstance(group, str) and group else None


def call_in_own_group(header_value: str, settings: Settings) -> bool:
    """Whether an incoming call may pass on the group it came through.

    Only an example instance knows its group; an instance for real work
    relies on the registry and on its FSC group, which an example peer has
    no certificate for.
    """
    if not settings.is_example:
        return True
    return token_group(header_value) == settings.EXAMPLE_FSC_GROUP.strip()
