"""The stream for other systems: CloudEvents, a cursor, closed by default."""

from __future__ import annotations

import re
import uuid
from datetime import datetime

import pytest

from grip.core.config import get_settings
from grip.events import cloudevents, logboek, stream
from grip.models.stream_event import StreamEvent
from grip.services import events as domain_events

_TYPE = re.compile(r"^nl\.grip(\.[a-z0-9-]+){2}$")
_OIN = "00000001234567890000"


@pytest.fixture
def feed_key(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "EVENTS_FEED_KEY", "sleutel-voor-de-test")
    monkeypatch.setattr(settings, "INSTANCE_OIN", _OIN)
    return {"Authorization": "Bearer sleutel-voor-de-test"}


async def test_the_feed_is_closed_by_default(client):
    assert not get_settings().EVENTS_FEED_KEY
    for headers in ({}, {"Authorization": "Bearer "}, {"Authorization": "Bearer raad"}):
        answer = await client.get("/api/gebeurtenissen", headers=headers)
        assert answer.status_code == 403


async def test_a_wrong_key_opens_nothing(client, feed_key):
    answer = await client.get(
        "/api/gebeurtenissen", headers={"Authorization": "Bearer verkeerd"}
    )
    assert answer.status_code == 403


async def test_events_follow_the_nl_gov_profile(client, db_session, feed_key, world):
    await domain_events.emit(
        db_session,
        domain_events.QUOTE_ACCEPTED,
        {
            "quote_id": str(uuid.uuid4()),
            "assignment_id": str(world.assignment.id),
            "signer": {"name": "Sam Voorbeeld", "email": "sam@example.org"},
        },
    )
    await db_session.flush()
    body = (await client.get("/api/gebeurtenissen", headers=feed_key)).json()
    assert body["gebeurtenissen"]
    ids = set()
    for event in body["gebeurtenissen"]:
        # Required by CloudEvents 1.0 and the NL GOV profile.
        assert event["specversion"] == "1.0"
        assert uuid.UUID(event["id"])
        assert event["source"] == f"urn:nld:oin:{_OIN}:systeem:grip-lokaal"
        assert _TYPE.match(event["type"]), event["type"]
        # Optional attributes the profile describes.
        assert datetime.fromisoformat(event["time"]).tzinfo is not None
        assert event["datacontenttype"] == "application/json"
        assert event["sequence"].isdigit() and event["sequencetype"] == "Integer"
        assert isinstance(event["subject"], str) and event["subject"]
        ids.add((event["source"], event["id"]))
        # Dutch at the edge, nothing of the values.
        assert set(event["data"]) <= {
            "onderwerp",
            "zaak",
            "actor",
            "herkomst",
            "herkomst_instantie",
            "correlatie",
            "hash",
            "vorige_hash",
            "aantal_gewijzigde_velden",
        }
    assert len(ids) == len(body["gebeurtenissen"])
    accepted = body["gebeurtenissen"][-1]
    assert accepted["type"] == "nl.grip.offerte.aanvaard"
    assert accepted["data"]["zaak"] == {
        "soort": "opdracht",
        "id": str(world.assignment.id),
    }
    assert "Sam" not in str(body) and "example.org" not in str(body)


async def test_the_cursor_gives_everything_after_it_in_order(
    client, db_session, feed_key
):
    start = (await client.get("/api/gebeurtenissen", headers=feed_key)).json()
    cursor = start["volgende"]
    while start["meer"]:
        start = (
            await client.get(
                "/api/gebeurtenissen", headers=feed_key, params={"na": cursor}
            )
        ).json()
        cursor = start["volgende"]
    written = [
        stream.append(db_session, subject=("rate_card", f"c{index}"), action="update")
        for index in range(7)
    ]
    await db_session.flush()

    seen: list[str] = []
    for _ in range(10):
        page = (
            await client.get(
                "/api/gebeurtenissen",
                headers=feed_key,
                params={"na": cursor, "limiet": 3},
            )
        ).json()
        seen += [event["sequence"] for event in page["gebeurtenissen"]]
        cursor = page["volgende"]
        if not page["meer"]:
            break
    assert seen == [str(event.seq) for event in written]
    # Nothing new: the cursor stays where it is.
    again = (
        await client.get("/api/gebeurtenissen", headers=feed_key, params={"na": cursor})
    ).json()
    assert again == {"gebeurtenissen": [], "volgende": cursor, "meer": False}


def test_every_known_type_has_a_dutch_name():
    from grip.events.classification import SPECS

    assert set(SPECS) <= set(cloudevents.KINDS)
    for internal in domain_events.EVENT_TYPES:
        translated = cloudevents.event_type(internal)
        assert _TYPE.match(translated), (internal, translated)
        kind, _, verb = internal.partition(".")
        assert kind in cloudevents.KINDS and verb in cloudevents.VERBS, internal


def test_without_an_oin_the_source_is_the_address_of_the_instance():
    settings = get_settings()
    assert not settings.INSTANCE_OIN
    assert cloudevents.source(settings) == settings.INSTANCE_BASE_URI.rstrip("/")


def test_an_event_maps_onto_a_log_record_of_logboek_dataverwerkingen():
    settings = get_settings()
    person_id = uuid.uuid4()
    event = StreamEvent(
        seq=7,
        id=uuid.uuid4(),
        occurred_at=datetime.fromisoformat("2026-10-08T10:00:00+00:00"),
        type="data.read",
        subject_kind="person",
        subject_id=str(person_id),
        person_id=person_id,
        correlation_id="4bf92f3577b34da6a3ce929d0e0e4736",
        origin="local",
    )
    record = logboek.to_log_record(event, settings)
    assert re.fullmatch(r"[0-9a-f]{32}", record["trace_id"])
    assert re.fullmatch(r"[0-9a-f]{16}", record["span_id"])
    assert record["status"] in {"Unset", "Ok", "Error"}
    assert record["name"] == "data.read"
    assert record["start_time"] == record["end_time"] == 1791453600000
    attributes = record["attributes"]
    assert attributes["dpl.core.processing_activity_id"].startswith("http")
    assert attributes["dpl.core.data_subject_id_type"]
    # The person is named by a pseudonym, never by the id itself.
    assert re.fullmatch(r"[0-9a-f]{64}", attributes["dpl.core.data_subject_id"])
    assert str(person_id) not in str(record)
    assert logboek.is_processing(event)
