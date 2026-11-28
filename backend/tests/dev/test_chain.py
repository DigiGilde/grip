"""Both halves of an assignment between example instances agree.

Each instance fills itself from its own dataset. For every assignment of the
chain the test fills the contractor's instance, then empties the database and
fills the client's, with the addresses each would have, and compares: the
URI, the parent, who it is shared with, and the lines and total of the quote.
"""

from __future__ import annotations

import inspect
import re

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grip.core.config import Settings, get_settings
from grip.dev import seed as seed_module
from grip.dev.datasets import NAMES, chain
from grip.dev.seed import seed
from grip.federation.models import FederationOutbox
from grip.models.assignment import Assignment, BudgetLine
from grip.models.organisation import Organisation
from grip.models.quote import Quote
from grip.services import events

ADDRESSES = {key: f"https://{key}.voorbeeld.example" for key in chain.INSTANCES}


@pytest.fixture(autouse=True)
def _no_event_handlers():
    events.clear_handlers()
    yield
    events.clear_handlers()


def _as(key: str) -> Settings:
    """The settings of the instance ``key`` in a deployed example group."""
    return get_settings().model_copy(
        update={
            "INSTANCE_BASE_URI": ADDRESSES[key],
            "EXAMPLE_INSTANCE_URIS": ",".join(
                f"{other}={uri}" for other, uri in ADDRESSES.items()
            ),
        }
    )


async def _side(db: AsyncSession, key: str, name: str, *, reset: bool):
    instance = chain.INSTANCES[key]
    await seed(db, settings=_as(key), dataset=instance.dataset, reset=reset)
    assignment = (
        await db.execute(select(Assignment).where(Assignment.name == name))
    ).scalar_one()
    quote = (
        await db.execute(
            select(Quote).where(
                Quote.assignment_id == assignment.id, Quote.status == "accepted"
            )
        )
    ).scalar_one()
    return assignment, quote.snapshot


@pytest.mark.parametrize("key", list(chain.SHARED))
async def test_both_sides_of_an_assignment_agree(db_session: AsyncSession, key: str):
    shared = chain.SHARED[key]
    contractor, issued = await _side(
        db_session, shared.contractor, shared.name, reset=False
    )
    seen = {
        "uri": contractor.uri,
        "parent": contractor.parent_assignment_uri,
        "status": contractor.status,
        "shared_with": contractor.shared_with_instance_uri,
    }
    client, received = await _side(db_session, shared.client, shared.name, reset=True)

    assert client.uri == seen["uri"]
    assert client.uri == f"{ADDRESSES[shared.client]}/id/opdracht/{shared.id}"
    assert client.parent_assignment_uri == seen["parent"]
    assert client.status == seen["status"] == "in_progress"
    assert seen["shared_with"] == ADDRESSES[shared.client]
    assert client.shared_with_instance_uri == ADDRESSES[shared.contractor]
    for part in ("lines", "subtotals_per_year", "total"):
        assert received[part] == issued[part], part
    # The client keeps no budget of the contractor.
    lines = await db_session.execute(
        select(BudgetLine.id).where(BudgetLine.assignment_id == client.id)
    )
    assert lines.all() == []


def test_every_instance_has_a_dataset_and_every_party_an_instance():
    assert {i.dataset for i in chain.INSTANCES.values()} == {
        seed_module.DEFAULT_DATASET,
        *NAMES,
    }
    for shared in chain.SHARED.values():
        assert shared.client in chain.INSTANCES
        assert shared.contractor in chain.INSTANCES
        assert shared.parent is None or shared.parent in chain.SHARED
    assert len({shared.id for shared in chain.SHARED.values()}) == len(chain.SHARED)


async def test_the_approval_covers_what_bzk_gives(db_session: AsyncSession):
    """What GDI approved is what BZK passes on: the programme and the execution."""
    book = chain.rate_book(seed_module.RATES, seed_module.SCALES)
    approved = chain.priced(chain.SHARED["delegation"], book)["total"]
    given = sum(
        chain.priced(chain.SHARED[key], book)["total"]["amount_cents"]
        for key in ("programme", "execution")
    )
    assert approved["amount_cents"] == given


@pytest.mark.parametrize("key", list(chain.INSTANCES))
async def test_an_instance_loads_only_its_own_side(db_session: AsyncSession, key: str):
    """No dataset loads the data of another: only the assignments it is party to,
    and only the organisations it deals with."""
    instance = chain.INSTANCES[key]
    await seed(db_session, settings=_as(key), dataset=instance.dataset)
    names = set((await db_session.execute(select(Assignment.name))).scalars())
    for shared in chain.SHARED.values():
        party = key in (shared.client, shared.contractor)
        assert (shared.name in names) is party, shared.name
    own = (
        await db_session.execute(
            select(Organisation).where(Organisation.instance_uri == ADDRESSES[key])
        )
    ).scalar_one()
    assert (own.name, own.tooi_uri, own.unit_key) == (
        instance.name,
        instance.tooi_uri,
        instance.unit_key,
    )
    # The parent is in the data where the dataset knows it.
    rows = {
        row.id: row
        for row in (await db_session.execute(select(Organisation))).scalars()
    }
    for row in rows.values():
        child = next(
            (
                i
                for i in chain.INSTANCES.values()
                if row.instance_uri == ADDRESSES[i.key]
            ),
            None,
        )
        if child is None or child.parent is None:
            continue
        known = {r.instance_uri for r in rows.values() if r.instance_uri is not None}
        if ADDRESSES[child.parent] in known:
            assert rows[row.parent_id].instance_uri == ADDRESSES[child.parent]
    # Filling sends nothing: the other side holds its own half.
    assert (await db_session.execute(select(FederationOutbox))).scalars().all() == []


@pytest.mark.parametrize("module", ["chain", *NAMES])
def test_no_address_in_a_dataset_uses_a_real_domain(module: str):
    import importlib

    source = inspect.getsource(importlib.import_module(f"grip.dev.datasets.{module}"))
    for domain in re.findall(r"@([a-z0-9.-]+\.[a-z]{2,})", source):
        assert domain.endswith((".example", ".invalid")), domain
