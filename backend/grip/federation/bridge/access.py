"""The access questions of the bridge, asked at the one decision point."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from grip.access import Context, LocalDecider
from grip.access.peer_deps import PeerAccess
from grip.access.sql import SqlRelationSource
from grip.core.config import get_settings
from grip.federation.bridge.settings import get_bridge_settings
from grip.federation.models import Peer


def peer_access(db: AsyncSession, peer: Peer) -> PeerAccess:
    relations = SqlRelationSource(
        db, instance_base_uri=get_settings().INSTANCE_BASE_URI
    )
    return PeerAccess(LocalDecider(relations), relations, peer.peer_id)


def pull_context(peer: Peer) -> Context:
    """The context of a pull by this peer.

    A pull is by its nature "on request". Whether financial data may be
    given is a property of the contract with the peer, which the beheerder
    records on the peer. Names in the hand-over are an instance setting.
    """
    return Context(
        on_request=True,
        contract_allows_financial=bool(peer.financial_inspection),
        parent_may_see_names=get_bridge_settings().HANDOVER_STAFFING_WITH_NAMES,
    )
