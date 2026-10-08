"""An issued quote keeps the words it was issued with, whatever the catalogue does."""

from sqlalchemy import select

from grip.models.assignment import BudgetLine
from grip.models.quote import Quote
from grip.services import catalogue_roles, quotes


def _personnel(snapshot) -> dict:
    return next(line for line in snapshot["lines"] if line["kind"] == "personnel")


async def test_rename_and_merge_leave_an_issued_quote_alone(
    db_session, rate_cards, beheerder, make_assignment, add_personnel_line
):
    assignment = await make_assignment()
    line = await add_personnel_line(assignment)
    line.role = "Productmanager"
    await db_session.flush()
    issued = await quotes.issue_quote(db_session, assignment.id, actor=beheerder)
    words = (
        _personnel(issued.snapshot)["role"],
        _personnel(issued.snapshot)["description"],
    )
    stored_hash, stored_canonical = issued.snapshot_hash, issued.canonical

    await catalogue_roles.update_role(
        db_session, line.role_id, {"name": "Product owner"}, actor=beheerder
    )
    other = await catalogue_roles.create_role(
        db_session, name="Producteigenaar", actor=beheerder
    )
    await catalogue_roles.merge_roles(
        db_session, line.role_id, other.id, actor=beheerder
    )

    stored = (
        await db_session.execute(select(Quote).where(Quote.id == issued.id))
    ).scalar_one()
    await db_session.refresh(stored)
    assert words[0] == "Productmanager"
    assert (
        _personnel(stored.snapshot)["role"],
        _personnel(stored.snapshot)["description"],
    ) == words
    assert (stored.snapshot_hash, stored.canonical) == (stored_hash, stored_canonical)
    # The line itself follows the catalogue, and so does the next quote.
    current = (
        await db_session.execute(select(BudgetLine).where(BudgetLine.id == line.id))
    ).scalar_one()
    await db_session.refresh(current)
    assert current.role == "Producteigenaar"
    again = await quotes.issue_quote(db_session, assignment.id, actor=beheerder)
    assert _personnel(again.snapshot)["role"] == "Producteigenaar"
