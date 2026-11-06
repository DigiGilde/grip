"""Correcting the day a recorded signed pdf was signed, through the route.

The quote is made on 2 March and it is 10 March now, so the days in between can
be true. All names are fictional.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from grip.chronicle.verify import differences
from grip.core import clock
from grip.repositories.chronicle import ChronicleRepository
from grip.services import assignments

PDF_BYTES = b"%PDF-1.4\n%voorbeeld\n"
ISSUED = datetime(2026, 3, 2, 15, 0, tzinfo=UTC)
TODAY = datetime(2026, 3, 10, 10, 0, tzinfo=UTC)
SIGNED = "2026-03-05T12:00:00+00:00"
CORRECTED = "2026-03-04T12:00:00+00:00"
# Midnight in the zone of the instance, which is an hour ahead of UTC in March.
START_OF_ISSUE_DAY = "2026-03-01T23:00:00+00:00"
START_OF_TOMORROW = "2026-03-10T23:00:00+00:00"

AFTER_TODAY = (
    START_OF_TOMORROW,
    "2099-01-01T12:00:00+00:00",
    "9999-12-31T12:00:00+00:00",
    "9999-12-31T23:59:59+00:00",
    "9999-12-31T23:59:59-14:00",
)
BEFORE_THE_QUOTE = (
    "2026-03-01T22:59:59+00:00",
    "2026-03-01",
    "2001-01-01T12:00:00+00:00",
    "0001-01-01T00:00:00+00:00",
    "0001-01-01T00:00:00+14:00",
)


@pytest.fixture(autouse=True)
def _days_after_the_quote():
    with clock.at(TODAY):
        yield


async def _issued(act_as, world) -> dict:
    with clock.at(ISSUED):
        issued = await act_as(world.manager).post(
            f"/api/assignments/{world.assignment.id}/quotes", json={}
        )
    assert issued.status_code == 201, issued.text
    return issued.json()


async def _upload(client, quote: dict, **data):
    return await client.post(
        f"/api/quotes/{quote['id']}/acceptance/uploaded-pdf",
        data={
            "signer_name": "Directeur Voorbeeld",
            "signer_email": "directeur@opdrachtgever.example",
            **data,
        },
        files={"file": ("getekend.pdf", PDF_BYTES, "application/pdf")},
    )


async def _accepted(act_as, world) -> dict:
    quote = await _issued(act_as, world)
    upload = await _upload(act_as(world.manager), quote, signed_at=SIGNED)
    assert upload.status_code == 201, upload.text
    return upload.json()


async def _correct(client, quote: dict, signed_at: str = CORRECTED, **more):
    return await client.post(
        f"/api/quotes/{quote['id']}/acceptance/correction",
        json={"signed_at": signed_at, "reason": "Datum verkeerd overgenomen", **more},
    )


async def _facts(db_session, world) -> list[str]:
    grams = await ChronicleRepository(db_session).grams(world.assignment.id)
    return [gram.fact for gram in grams]


async def _signed_day(act_as, world, quote: dict) -> str:
    body = (await act_as(world.manager).get(f"/api/quotes/{quote['id']}")).json()
    return body["acceptance"]["signed_at"][:10]


async def test_the_day_is_corrected_with_a_reason(act_as, world, db_session):
    quote = await _accepted(act_as, world)
    client = act_as(world.manager)
    response = await client.post(
        f"/api/quotes/{quote['id']}/acceptance/correction",
        json={"signed_at": CORRECTED, "reason": "Datum verkeerd overgenomen"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == quote["id"] and body["status"] == "accepted"
    assert datetime.fromisoformat(body["acceptance"]["signed_at"]) == datetime(
        2026, 3, 4, 12, 0, tzinfo=UTC
    )
    assert body["acceptance"]["signer_name"] == "Directeur Voorbeeld"
    grams = await ChronicleRepository(db_session).grams(world.assignment.id)
    assert grams[-1].fact == "acceptance_date_corrected"
    assert grams[-1].actor_person_id == world.manager.id
    report = await differences(db_session, world.assignment.id)
    assert report.checked and report.differences == []


async def test_a_day_without_a_time_or_zone_is_taken(act_as, world):
    quote = await _accepted(act_as, world)
    response = await act_as(world.manager).post(
        f"/api/quotes/{quote['id']}/acceptance/correction",
        json={"signed_at": "2026-03-04", "reason": "Datum verkeerd overgenomen"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["acceptance"]["signed_at"].startswith("2026-03-04")


async def test_a_reason_is_needed(act_as, world):
    quote = await _accepted(act_as, world)
    client = act_as(world.manager)
    blank = await client.post(
        f"/api/quotes/{quote['id']}/acceptance/correction",
        json={"signed_at": CORRECTED, "reason": "   "},
    )
    assert blank.status_code == 422
    assert "waarom" in blank.json()["detail"]
    missing = await client.post(
        f"/api/quotes/{quote['id']}/acceptance/correction",
        json={"signed_at": CORRECTED},
    )
    assert missing.status_code == 422


async def test_only_who_may_record_it_may_correct_it(act_as, world):
    quote = await _accepted(act_as, world)
    for person in (world.lezer, world.planner, world.beheerder):
        response = await act_as(person).post(
            f"/api/quotes/{quote['id']}/acceptance/correction",
            json={"signed_at": CORRECTED, "reason": "Voorbeeld"},
        )
        assert response.status_code == 403, person.email
    hidden = await act_as(world.outsider).post(
        f"/api/quotes/{quote['id']}/acceptance/correction",
        json={"signed_at": CORRECTED, "reason": "Voorbeeld"},
    )
    assert hidden.status_code == 404


async def test_a_quote_without_an_acceptance_is_404(act_as, world):
    client = act_as(world.manager)
    issued = await client.post(
        f"/api/assignments/{world.assignment.id}/quotes", json={}
    )
    response = await client.post(
        f"/api/quotes/{issued.json()['id']}/acceptance/correction",
        json={"signed_at": CORRECTED, "reason": "Voorbeeld"},
    )
    assert response.status_code == 404


async def test_a_signed_link_is_not_corrected(act_as, world, db_session):
    from grip.services import quote_views

    client = act_as(world.manager)
    issued = (
        await client.post(f"/api/assignments/{world.assignment.id}/quotes", json={})
    ).json()
    invited = await client.post(
        f"/api/quotes/{issued['id']}/invitations",
        json={"email": world.signer.email},
    )
    assert invited.status_code == 201, invited.text
    await quote_views.accept_via_signing_link(
        db_session,
        issued["id"],
        quote_hash=issued["snapshot_hash"],
        signer_name=world.signer.name,
        signer_email=world.signer.email,
        signer_person_id=world.signer.id,
    )
    response = await client.post(
        f"/api/quotes/{issued['id']}/acceptance/correction",
        json={"signed_at": CORRECTED, "reason": "Voorbeeld"},
    )
    assert response.status_code == 422


# -- a day that cannot be true ------------------------------------------------


@pytest.mark.parametrize("moment", AFTER_TODAY)
async def test_a_correction_to_after_today_is_refused(
    act_as, world, db_session, moment
):
    quote = await _accepted(act_as, world)
    facts = await _facts(db_session, world)
    response = await _correct(act_as(world.manager), quote, moment)
    assert response.status_code == 422, response.text
    assert "toekomst" in response.json()["detail"]
    assert await _facts(db_session, world) == facts
    assert await _signed_day(act_as, world, quote) == SIGNED[:10]


@pytest.mark.parametrize("moment", BEFORE_THE_QUOTE)
async def test_a_correction_to_before_the_quote_is_refused(
    act_as, world, db_session, moment
):
    quote = await _accepted(act_as, world)
    facts = await _facts(db_session, world)
    response = await _correct(act_as(world.manager), quote, moment)
    assert response.status_code == 422, response.text
    assert "voor de dag waarop de offerte is gemaakt" in response.json()["detail"]
    assert await _facts(db_session, world) == facts
    assert await _signed_day(act_as, world, quote) == SIGNED[:10]


@pytest.mark.parametrize(
    ("moment", "word"),
    [
        *((moment, "toekomst") for moment in AFTER_TODAY),
        *((moment, "voor de dag waarop") for moment in BEFORE_THE_QUOTE),
    ],
)
async def test_an_upload_with_such_a_day_records_nothing(
    act_as, world, db_session, moment, word
):
    quote = await _issued(act_as, world)
    facts = await _facts(db_session, world)
    client = act_as(world.manager)
    response = await _upload(client, quote, signed_at=moment)
    assert response.status_code == 422, response.text
    assert word in response.json()["detail"]
    assert await _facts(db_session, world) == facts
    body = (await client.get(f"/api/quotes/{quote['id']}")).json()
    assert body["status"] == "issued" and body["acceptance"] is None


@pytest.mark.parametrize(
    ("moment", "day"),
    [
        (START_OF_ISSUE_DAY, "2026-03-02"),
        ("2026-03-02T00:00:00+01:00", "2026-03-02"),
        ("2026-03-10T22:59:59+00:00", "2026-03-10"),
        ("2026-03-10T12:00:00+00:00", "2026-03-10"),
        # Another date than in UTC, on the calendar of the instance.
        ("2026-03-05T23:30:00+00:00", "2026-03-06"),
    ],
)
async def test_the_day_of_the_quote_and_today_can_be_true(
    act_as, world, db_session, moment, day
):
    quote = await _accepted(act_as, world)
    response = await _correct(act_as(world.manager), quote, moment)
    assert response.status_code == 200, response.text
    grams = await ChronicleRepository(db_session).grams(world.assignment.id)
    assert grams[-1].effective_on == day


@pytest.mark.parametrize(
    "moment", [START_OF_ISSUE_DAY, "2026-03-10T22:59:59+00:00", None]
)
async def test_an_upload_on_the_day_of_the_quote_or_today_is_taken(
    act_as, world, moment
):
    quote = await _issued(act_as, world)
    response = await _upload(
        act_as(world.manager), quote, **({"signed_at": moment} if moment else {})
    )
    assert response.status_code == 201, response.text


@pytest.mark.parametrize(
    "moment",
    [
        SIGNED,
        "2026-03-05T13:00:00+01:00",
        "2026-03-05T18:00:00+00:00",
        # Another date in UTC, the same on the calendar of the instance.
        "2026-03-04T23:30:00+00:00",
    ],
)
async def test_the_same_day_is_refused_in_the_words_of_the_sheet(
    act_as, world, db_session, moment
):
    quote = await _accepted(act_as, world)
    facts = await _facts(db_session, world)
    response = await _correct(act_as(world.manager), quote, moment)
    assert response.status_code == 422, response.text
    assert response.json()["detail"] == (
        "Dit is de datum die al is vastgelegd. Kies de juiste datum."
    )
    assert await _facts(db_session, world) == facts


# -- a correction on top of another -------------------------------------------


async def _second_manager(db_session, world):
    await assignments.set_assignment_role(
        db_session,
        world.assignment.id,
        world.planner.id,
        "manager",
        actor=world.manager,
    )
    return world.planner


async def test_a_form_that_started_from_an_older_date_is_told_who_was_first(
    act_as, world, db_session
):
    quote = await _accepted(act_as, world)
    other = await _second_manager(db_session, world)
    first = await _correct(act_as(world.manager), quote, expected_signed_at=SIGNED)
    assert first.status_code == 200, first.text
    facts = await _facts(db_session, world)

    stale = await _correct(
        act_as(other), quote, "2026-03-06T12:00:00+00:00", expected_signed_at=SIGNED
    )
    assert stale.status_code == 409, stale.text
    body = stale.json()
    assert body["code"] == "StaleWriteError"
    assert body["changed_by"] == "Opdracht Manager"
    assert body["changed_at"]
    assert body["detail"].startswith(
        "Opdracht Manager heeft de datum van tekenen intussen gewijzigd"
    )
    assert body["detail"].endswith("Er is niets overschreven.")
    assert await _facts(db_session, world) == facts
    assert await _signed_day(act_as, world, quote) == CORRECTED[:10]


@pytest.mark.parametrize(
    "expected",
    ["2026-03-06T12:00:00+00:00", "9999-12-31T23:59:59+00:00", "0001-01-01"],
)
async def test_any_other_date_than_the_one_that_stands_is_stale(
    act_as, world, expected
):
    quote = await _accepted(act_as, world)
    response = await _correct(act_as(world.manager), quote, expected_signed_at=expected)
    assert response.status_code == 409, response.text
    assert await _signed_day(act_as, world, quote) == SIGNED[:10]


@pytest.mark.parametrize(
    "expected",
    [
        {"expected_signed_at": SIGNED},
        # The same moment in another zone, and without a zone.
        {"expected_signed_at": "2026-03-05T13:00:00+01:00"},
        {"expected_signed_at": "2026-03-05T12:00:00"},
        {"expected_signed_at": None},
        # As a save without If-Match: not compared.
        {},
    ],
)
async def test_a_form_on_the_date_that_stands_goes_through(act_as, world, expected):
    quote = await _accepted(act_as, world)
    response = await _correct(act_as(world.manager), quote, **expected)
    assert response.status_code == 200, response.text
    assert await _signed_day(act_as, world, quote) == CORRECTED[:10]


async def test_a_correction_without_the_date_it_started_from_still_says_what_stood(
    act_as, world, db_session
):
    quote = await _accepted(act_as, world)
    other = await _second_manager(db_session, world)
    await _correct(act_as(world.manager), quote)
    response = await _correct(act_as(other), quote, "2026-03-06T12:00:00+00:00")
    assert response.status_code == 200, response.text
    grams = await ChronicleRepository(db_session).grams(world.assignment.id)
    assert grams[-1].fields["was"].startswith(CORRECTED[:10])


# -- what the history says ----------------------------------------------------


async def _told(act_as, world, person, event_type: str) -> dict:
    response = await act_as(person).get(
        "/api/events",
        params={"case_id": str(world.assignment.id), "limit": 200},
    )
    assert response.status_code == 200, response.text
    return next(item for item in response.json()["items"] if item["type"] == event_type)


async def test_the_history_says_a_signed_pdf_was_recorded(act_as, world):
    await _accepted(act_as, world)

    for reader in (world.manager, world.lezer, world.planner):
        told = await _told(act_as, world, reader, "quote.accepted")
        assert told["title"] == "Getekende pdf vastgelegd"


async def test_the_history_says_which_date_was_corrected(act_as, world):
    quote = await _accepted(act_as, world)
    corrected = await _correct(act_as(world.manager), quote)
    assert corrected.status_code == 200, corrected.text

    for reader in (world.manager, world.lezer):
        told = await _told(act_as, world, reader, "quote_acceptance.updated")
        assert "Datum van tekenen van 5 maart 2026 naar 4 maart 2026" in told["lines"]
    told = await _told(act_as, world, world.planner, "quote_acceptance.updated")
    assert told["lines"] == []


async def test_the_history_says_the_day_on_the_calendar_of_the_instance(act_as, world):
    quote = await _issued(act_as, world)
    client = act_as(world.manager)
    upload = await _upload(client, quote, signed_at="2026-03-05T23:30:00+00:00")
    assert upload.status_code == 201, upload.text
    corrected = await _correct(client, quote)
    assert corrected.status_code == 200, corrected.text

    told = await _told(act_as, world, world.manager, "quote_acceptance.created")
    assert "Datum van tekenen 6 maart 2026" in told["lines"]
    told = await _told(act_as, world, world.manager, "quote_acceptance.updated")
    assert "Datum van tekenen van 6 maart 2026 naar 4 maart 2026" in told["lines"]
