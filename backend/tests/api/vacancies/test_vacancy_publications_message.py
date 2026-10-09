"""A vacancy that goes to other instances says where anyone can read it."""

from __future__ import annotations

from datetime import UTC, date, datetime

from grip.federation.bridge import builders
from grip.federation.contract_loader import validator_for
from grip.models.vacancy import Vacancy, VacancyStatus
from grip.models.vacancy_text_flow import (
    PLACE_EXTERNAL,
    PLACE_GOVERNMENT_WIDE,
    PLACE_INTERNAL,
    VacancyPublication,
)
from grip.services import terms
from tests.api.vacancies.test_vacancies_api import BASE, _create


def _publication_errors(contract: dict) -> list[str]:
    """What the contract says against the places. The test instance has no
    identity of its own configured, so the rest of the message is not judged
    here."""
    return [
        error.message
        for error in validator_for("vacature").iter_errors(contract)
        if error.absolute_path and error.absolute_path[0] == "publicaties"
    ]


async def _open_vacancy(client, act_as, manager, budget_line, db_session):
    act_as(manager)
    vacancy = await _create(client, budget_line)
    response = await client.post(
        f"{BASE}/{vacancy['id']}/texts",
        json={"kind": "vacancy_text", "body": "Een fictieve vacaturetekst."},
    )
    assert response.status_code in (200, 201), response.text
    text_id = response.json()["texts"][-1]["id"]
    row = await db_session.get(Vacancy, vacancy["id"])
    row.status = VacancyStatus.open.value
    row.published_at = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
    await db_session.flush()
    return row, text_id


async def _message(db_session, vacancy, text_id) -> dict:
    built = await builders.vacancy_published(
        db_session,
        {
            "vacancy_id": str(vacancy.id),
            "text_id": text_id,
            "channels": ["federated"],
            "origin": "local",
        },
    )
    assert built is not None
    return built["message"]


async def test_the_message_lists_the_public_places_in_contract_words(
    client, act_as, manager, budget_line, db_session
) -> None:
    vacancy, text_id = await _open_vacancy(
        client, act_as, manager, budget_line, db_session
    )
    for place, day in (
        (PLACE_EXTERNAL, date(2026, 10, 9)),
        (PLACE_INTERNAL, date(2026, 10, 1)),
        (PLACE_GOVERNMENT_WIDE, date(2026, 10, 5)),
    ):
        db_session.add(
            VacancyPublication(
                vacancy_id=vacancy.id,
                place=place,
                url=f"https://werken.voorbeeld.example/{place}",
                published_on=day,
            )
        )
    await db_session.flush()

    message = await _message(db_session, vacancy, text_id)
    contract = terms.to_contract(message)
    assert contract["publicaties"] == [
        {
            "plek": "intern",
            "url": "https://werken.voorbeeld.example/internal",
            "gepubliceerd_op": "2026-10-01",
        },
        {
            "plek": "rijksbreed",
            "url": "https://werken.voorbeeld.example/government_wide",
            "gepubliceerd_op": "2026-10-05",
        },
        {
            "plek": "extern",
            "url": "https://werken.voorbeeld.example/external",
            "gepubliceerd_op": "2026-10-09",
        },
    ]
    assert _publication_errors(contract) == []
    # And back, a receiving instance reads the same places.
    assert terms.from_contract(contract)["publications"] == message["publications"]


async def test_a_vacancy_that_is_published_nowhere_has_no_list(
    client, act_as, manager, budget_line, db_session
) -> None:
    vacancy, text_id = await _open_vacancy(
        client, act_as, manager, budget_line, db_session
    )
    message = await _message(db_session, vacancy, text_id)
    assert "publications" not in message
    assert _publication_errors(terms.to_contract(message)) == []
