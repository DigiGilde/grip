"""Notifications on a device: what is sent, to whom, when, and what it says.

A push service is played by a fake HTTP client that keeps what it is sent;
the body is decrypted with a library that is not ours (http-ece), with the
keys a browser would hold. All names are fictional.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import http_ece
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from sqlalchemy import select, text

from grip.core.config import Settings, get_settings
from grip.integrations.push import keys, outbox, scan, webpush
from grip.integrations.push.config import b64url, public_point, push_config
from grip.models.audit_log import AuditLog
from grip.models.push import (
    KIND_OVERDUE,
    KIND_QUOTE_ACCEPTED,
    KIND_TASKS,
    PUSH_QUEUED,
    PUSH_SENT,
    PUSH_SKIPPED,
    PushNotice,
    PushOutbox,
    PushSubscription,
)
from grip.models.task import Task
from grip.services import events as domain_events
from grip.services import notifications
from grip.services.notifications import Preference

AMSTERDAM = ZoneInfo("Europe/Amsterdam")
# A Tuesday at eleven in the morning, Amsterdam: not quiet.
NOON = datetime(2026, 10, 6, 11, 0, tzinfo=AMSTERDAM).astimezone(UTC)
PRIVATE_KEY, PUBLIC_KEY = keys.generate()


@pytest.fixture
def settings() -> Settings:
    return get_settings().model_copy(
        update={"PUSH_VAPID_PRIVATE_KEY": PRIVATE_KEY, "PUSH_BATCH_SECONDS": 90}
    )


@pytest.fixture
def push_on(_test_app, settings):
    _test_app.dependency_overrides[get_settings] = lambda: settings
    yield settings
    _test_app.dependency_overrides.pop(get_settings, None)


class Browser:
    """The keys a browser holds for one subscription."""

    def __init__(self, name: str = "a") -> None:
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.auth = os.urandom(16)
        self.endpoint = f"https://push.test.example/send/{name}-{uuid.uuid4()}"

    def as_json(self, label: str = "Laptop") -> dict:
        return {
            "endpoint": self.endpoint,
            "keys": {
                "p256dh": b64url(public_point(self.key)),
                "auth": b64url(self.auth),
            },
            "label": label,
        }

    def read(self, body: bytes) -> dict:
        return json.loads(
            http_ece.decrypt(
                body, private_key=self.key, auth_secret=self.auth, version="aes128gcm"
            )
        )


class PushService:
    """Keeps every request; answers what the test tells it to."""

    def __init__(self) -> None:
        self.requests: list[tuple[str, dict, bytes]] = []
        self.status: dict[str, int] = {}

    async def post(self, url, *, content, headers, timeout):
        self.requests.append((url, headers, content))

        class Answer:
            status_code = self.status.get(url, 201)

        return Answer()


async def _device(db_session, person, browser: Browser | None = None) -> Browser:
    browser = browser or Browser()
    await notifications.add_device(
        db_session,
        person,
        endpoint=browser.endpoint,
        p256dh=b64url(public_point(browser.key)),
        auth=b64url(browser.auth),
        label="Laptop",
    )
    return browser


async def _task(
    db_session,
    world,
    person,
    *,
    created: datetime,
    due: date | None = None,
    title: str = "Bel de opdrachtgever",
    by=None,
) -> Task:
    task = Task(
        case_kind="assignment",
        assignment_id=world.assignment.id,
        origin="manual",
        title=title,
        track="general",
        assignee_person_id=person.id,
        created_by_id=by.id if by is not None else None,
        due_on=due,
        status="todo",
    )
    db_session.add(task)
    await db_session.flush()
    await db_session.execute(
        text("update task set created_at = :at where id = :id"),
        {"at": created, "id": task.id},
    )
    await db_session.refresh(task)
    return task


async def _queued(db_session, person) -> list[PushOutbox]:
    rows = await db_session.scalars(
        select(PushOutbox)
        .where(PushOutbox.person_id == person.id)
        .order_by(PushOutbox.created_at)
    )
    return list(rows)


# --- the protocol ---------------------------------------------------------------


def test_a_message_is_encrypted_for_one_browser_and_says_who_sends(settings):
    config = push_config(settings)
    browser = Browser()
    target = webpush.Target(
        **{
            k: v
            for k, v in {
                "endpoint": browser.endpoint,
                "p256dh": b64url(public_point(browser.key)),
                "auth": b64url(browser.auth),
            }.items()
        }
    )
    headers, body = webpush.request_for(
        config, target, {"k": "tasks", "n": 2}, topic="tasks"
    )
    # Only this browser reads it; another one cannot.
    assert browser.read(body) == {"k": "tasks", "n": 2}
    with pytest.raises(Exception):
        Browser().read(body)
    assert b"tasks" not in body
    assert headers["Content-Encoding"] == "aes128gcm"
    assert headers["Topic"] == "tasks" and int(headers["TTL"]) > 0

    # The token is signed by the instance's key, for this push service only.
    scheme, rest = headers["Authorization"].split(" ", 1)
    parts = dict(item.strip().split("=", 1) for item in rest.split(","))
    assert scheme == "vapid" and parts["k"] == PUBLIC_KEY == config.public_key
    header, claims, signature = parts["t"].split(".")
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

    from grip.integrations.push.config import b64url_decode

    raw = b64url_decode(signature)
    config.private_key.public_key().verify(
        encode_dss_signature(
            int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big")
        ),
        f"{header}.{claims}".encode(),
        ec.ECDSA(hashes.SHA256()),
    )
    said = json.loads(b64url_decode(claims))
    assert said["aud"] == "https://push.test.example"
    assert said["exp"] > datetime.now(UTC).timestamp()


def test_without_a_key_pair_nothing_is_configured():
    assert push_config(get_settings()) is None


# --- quiet hours ------------------------------------------------------------------


def test_quiet_hours_run_over_midnight_and_over_the_weekend():
    preference = Preference()

    def at(day: int, hour: int, minute: int = 0) -> datetime:
        return datetime(2026, 10, day, hour, minute, tzinfo=AMSTERDAM)

    # Tuesday 6 October 2026.
    assert preference.resumes_at(at(6, 11), AMSTERDAM) is None
    assert preference.resumes_at(at(6, 20), AMSTERDAM) == at(7, 7, 30).astimezone(UTC)
    assert preference.resumes_at(at(6, 6), AMSTERDAM) == at(6, 7, 30).astimezone(UTC)
    # Friday evening runs through the weekend to Monday morning.
    assert preference.resumes_at(at(9, 21), AMSTERDAM) == at(12, 7, 30).astimezone(UTC)
    assert preference.resumes_at(at(10, 12), AMSTERDAM) == at(12, 7, 30).astimezone(UTC)
    never = Preference(quiet_from=None, quiet_until=None, weekends_quiet=False)
    assert never.resumes_at(at(10, 3), AMSTERDAM) is None


# --- what is noticed -------------------------------------------------------------


async def test_a_task_that_becomes_yours_is_one_notice_and_only_once(
    world, db_session, settings
):
    browser = await _device(db_session, world.manager)
    task = await _task(
        db_session, world, world.manager, created=NOON - timedelta(minutes=5)
    )

    assert await scan.scan_tasks(db_session, settings, now=NOON) == 1
    assert (
        await scan.scan_tasks(db_session, settings, now=NOON + timedelta(minutes=2))
        == 0
    )
    (row,) = await _queued(db_session, world.manager)
    assert (row.kind, row.count, row.badge) == (KIND_TASKS, 1, 1)
    assert row.path == f"/taken?taak={task.id}"

    service = PushService()
    assert await outbox.send_due(db_session, settings, service, now=NOON) == 1
    (url, headers, body) = service.requests[0]
    assert url == browser.endpoint and headers["Topic"] == "tasks"
    assert browser.read(body) == {
        "v": 1,
        "k": "tasks",
        "n": 1,
        "p": f"/taken?taak={task.id}",
        "i": str(row.id),
        "b": 1,
    }
    assert row.status == PUSH_SENT


async def test_a_burst_is_held_and_becomes_one_notice(world, db_session, settings):
    await _device(db_session, world.manager)
    for minutes in (3, 2, 1):
        await _task(
            db_session,
            world,
            world.manager,
            created=NOON - timedelta(seconds=20 * minutes),
            title=f"Taak {minutes}",
        )
    # The youngest is twenty seconds old: more may follow.
    assert await scan.scan_tasks(db_session, settings, now=NOON) == 0
    assert (
        await scan.scan_tasks(db_session, settings, now=NOON + timedelta(minutes=2))
        == 1
    )
    (row,) = await _queued(db_session, world.manager)
    assert (row.count, row.badge, row.path) == (3, 3, "/taken")


async def test_what_you_caused_yourself_and_what_waits_on_others_is_not_noticed(
    world, db_session, settings
):
    await _device(db_session, world.manager)
    before = NOON - timedelta(minutes=5)
    # Added by the manager for the manager.
    await _task(db_session, world, world.manager, created=before, by=world.manager)
    # Theirs, but waiting on someone else.
    waiting = await _task(db_session, world, world.manager, created=before)
    waiting.status = "waiting"
    # Someone else's.
    await _task(db_session, world, world.planner, created=before)
    await db_session.flush()

    assert await scan.scan_tasks(db_session, settings, now=NOON) == 0
    assert await _queued(db_session, world.manager) == []
    # The own task is remembered as known, so it is not looked at again.
    notices = (await db_session.scalars(select(PushNotice))).all()
    assert [notice.notified for notice in notices] == [False]


async def test_a_task_past_its_date_is_noticed_once_more(world, db_session, settings):
    await _device(db_session, world.manager)
    await _task(
        db_session,
        world,
        world.manager,
        created=NOON - timedelta(days=3),
        due=NOON.date() + timedelta(days=1),
    )
    assert await scan.scan_tasks(db_session, settings, now=NOON) == 1
    later = NOON + timedelta(days=2)
    assert await scan.scan_tasks(db_session, settings, now=later) == 1
    assert (
        await scan.scan_tasks(db_session, settings, now=later + timedelta(days=1)) == 0
    )
    kinds = [row.kind for row in await _queued(db_session, world.manager)]
    assert kinds == [KIND_TASKS, KIND_OVERDUE]


async def test_what_already_waited_when_you_register_is_not_noticed(
    act_as, world, db_session, push_on
):
    await _task(db_session, world, world.manager, created=NOON - timedelta(days=1))
    client = act_as(world.manager)
    made = await client.post("/api/notifications/devices", json=Browser().as_json())
    assert made.status_code == 201, made.text
    assert await scan.scan_tasks(db_session, push_on, now=NOON) == 0
    await _task(db_session, world, world.manager, created=NOON - timedelta(minutes=5))
    assert await scan.scan_tasks(db_session, push_on, now=NOON) == 1


async def test_a_decision_on_your_quote_reaches_who_offered_it_not_who_decided(
    world, db_session, settings
):
    await _device(db_session, world.manager)
    await _device(db_session, world.beheerder)
    # The first look only notes where the stream stands.
    assert await scan.scan_decisions(db_session, settings) == 0
    await domain_events.emit(
        db_session,
        domain_events.QUOTE_ACCEPTED,
        {
            "quote_id": str(uuid.uuid4()),
            "assignment_id": str(world.assignment.id),
            "signer": {"name": "Gast Tekenaar", "email": "gast@example.org"},
        },
    )
    await db_session.flush()
    assert await scan.scan_decisions(db_session, settings) == 1
    assert await scan.scan_decisions(db_session, settings) == 0
    (row,) = await _queued(db_session, world.manager)
    assert row.kind == KIND_QUOTE_ACCEPTED
    assert row.path == f"/opdrachten/{world.assignment.id}/offerte"
    # The beheerder has a device but did not offer this quote.
    assert await _queued(db_session, world.beheerder) == []


# --- what a notice says -------------------------------------------------------------


async def test_nothing_on_the_wire_names_a_person_a_client_or_an_amount(
    world, db_session, settings
):
    browser = await _device(db_session, world.manager)
    await _task(
        db_session,
        world,
        world.manager,
        created=NOON - timedelta(minutes=5),
        title=f"Bel {world.signer.name} over 172.800 euro",
    )
    await scan.scan_tasks(db_session, settings, now=NOON)
    await scan.scan_decisions(db_session, settings)
    await domain_events.emit(
        db_session,
        domain_events.QUOTE_REJECTED,
        {
            "quote_id": str(uuid.uuid4()),
            "assignment_id": str(world.assignment.id),
            "reason": "Te duur: 172.800 euro",
        },
    )
    await db_session.flush()
    await scan.scan_decisions(db_session, settings, now=NOON)
    service = PushService()
    await outbox.send_due(db_session, settings, service, now=NOON)
    assert len(service.requests) == 2

    names = (await db_session.execute(text("select name from person"))).scalars().all()
    emails = (
        (await db_session.execute(text("select email from person"))).scalars().all()
    )
    forbidden = [
        *names,
        *[e for e in emails if e],
        world.assignment.name,
        "172",
        "euro",
        "Bel",
        "Te duur",
    ]
    for _url, headers, body in service.requests:
        payload = browser.read(body)
        # A fixed set of keys, and no free text among the values.
        assert set(payload) <= {"v", "k", "n", "p", "i", "b"}
        assert payload["k"] in ("tasks", "quote_rejected")
        said = json.dumps(payload) + json.dumps(headers)
        for word in forbidden:
            assert word not in said, word


# --- not noise --------------------------------------------------------------------


async def test_quiet_hours_keep_notices_and_send_them_as_one_afterwards(
    world, db_session, settings
):
    await _device(db_session, world.manager)
    evening = datetime(2026, 10, 6, 21, 0, tzinfo=AMSTERDAM).astimezone(UTC)
    for index in range(2):
        await outbox.enqueue(
            db_session,
            person_id=world.manager.id,
            kind=KIND_TASKS,
            dedupe_key=f"t{index}",
            count=1,
            path="/taken?taak=x",
            now=evening + timedelta(minutes=index),
        )
    service = PushService()
    assert (
        await outbox.send_due(
            db_session, settings, service, now=evening + timedelta(minutes=5)
        )
        == 0
    )
    assert service.requests == []
    morning = datetime(2026, 10, 7, 7, 31, tzinfo=AMSTERDAM).astimezone(UTC)
    assert await outbox.send_due(db_session, settings, service, now=morning) == 1
    rows = await _queued(db_session, world.manager)
    assert sorted(row.status for row in rows) == [PUSH_SENT, PUSH_SKIPPED]
    sent = next(row for row in rows if row.status == PUSH_SENT)
    assert (sent.count, sent.path) == (2, "/taken")


async def test_a_day_has_a_cap_and_a_switched_off_kind_is_not_sent(
    world, db_session, settings
):
    capped = settings.model_copy(update={"PUSH_DAILY_CAP": 2})
    await _device(db_session, world.manager)
    service = PushService()
    for index in range(3):
        await outbox.enqueue(
            db_session,
            person_id=world.manager.id,
            kind=KIND_QUOTE_ACCEPTED,
            dedupe_key=f"d{index}",
            now=NOON,
        )
        await outbox.send_due(
            db_session, capped, service, now=NOON + timedelta(minutes=index)
        )
    rows = await _queued(db_session, world.manager)
    assert [row.status for row in rows] == [PUSH_SENT, PUSH_SENT, PUSH_SKIPPED]
    assert rows[-1].last_error == "dagmaximum"

    await notifications.set_preference(db_session, world.manager, {"decisions": False})
    await outbox.enqueue(
        db_session,
        person_id=world.manager.id,
        kind=KIND_QUOTE_ACCEPTED,
        dedupe_key="uit",
        now=NOON + timedelta(days=1),
    )
    await outbox.send_due(db_session, settings, service, now=NOON + timedelta(days=1))
    assert (await _queued(db_session, world.manager))[-1].last_error == "staat uit"
    assert len(service.requests) == 2


async def test_a_device_the_push_service_no_longer_knows_is_removed(
    world, db_session, settings
):
    gone = await _device(db_session, world.manager, Browser("weg"))
    kept = await _device(db_session, world.manager, Browser("blijft"))
    service = PushService()
    service.status[gone.endpoint] = 410
    await outbox.enqueue(
        db_session,
        person_id=world.manager.id,
        kind=KIND_TASKS,
        dedupe_key="g",
        now=NOON,
    )
    assert await outbox.send_due(db_session, settings, service, now=NOON) == 1
    devices = await notifications.devices_of(db_session, world.manager.id)
    assert [device.endpoint for device in devices] == [kept.endpoint]
    assert devices[0].last_success_at is not None

    # A service that is down is tried again later, and the device stays.
    service.status[kept.endpoint] = 503
    await outbox.enqueue(
        db_session,
        person_id=world.manager.id,
        kind=KIND_OVERDUE,
        dedupe_key="h",
        now=NOON,
    )
    assert await outbox.send_due(db_session, settings, service, now=NOON) == 0
    row = (await _queued(db_session, world.manager))[-1]
    assert row.status == PUSH_QUEUED and row.next_attempt_at > NOON
    assert len(await notifications.devices_of(db_session, world.manager.id)) == 1


# --- the routes ----------------------------------------------------------------------


async def test_notifications_are_off_without_a_key_pair(act_as, world):
    client = act_as(world.manager)
    seen = (await client.get("/api/notifications")).json()
    assert seen["available"] is False and seen["public_key"] is None
    refused = await client.post("/api/notifications/devices", json=Browser().as_json())
    assert refused.status_code == 501
    # The preference can still be set: it also covers what comes by mail.
    saved = await client.put("/api/notifications/preference", json={"overdue": False})
    assert saved.status_code == 200 and saved.json()["overdue"] is False


async def test_a_person_manages_only_their_own_devices_and_never_sees_an_endpoint(
    act_as, world, db_session, push_on
):
    client = act_as(world.manager)
    browser = Browser()
    made = await client.post(
        "/api/notifications/devices", json=browser.as_json("Telefoon")
    )
    assert made.status_code == 201, made.text
    assert set(made.json()) == {"id", "label", "created_at", "last_success_at"}
    seen = (await client.get("/api/notifications")).json()
    assert seen["available"] is True and seen["public_key"] == PUBLIC_KEY
    assert [device["label"] for device in seen["devices"]] == ["Telefoon"]
    assert browser.endpoint not in json.dumps(seen)

    other = act_as(world.planner)
    assert (await other.get("/api/notifications")).json()["devices"] == []
    assert (
        await other.delete(f"/api/notifications/devices/{made.json()['id']}")
    ).status_code == 404

    # The same browser, now used by someone else: it notifies them from now on.
    again = await other.post("/api/notifications/devices", json=browser.as_json())
    assert again.status_code == 201
    stored = (await db_session.scalars(select(PushSubscription))).all()
    assert [device.person_id for device in stored] == [world.planner.id]

    assert (
        await other.delete(f"/api/notifications/devices/{again.json()['id']}")
    ).status_code == 204
    events = (
        await db_session.scalars(
            select(AuditLog).where(AuditLog.entity == "push_subscription")
        )
    ).all()
    assert [event.action for event in events] == ["create", "update", "delete"]
    # The address of the device is not in the stream.
    assert browser.endpoint not in json.dumps([event.new_value for event in events])

    not_https = Browser().as_json()
    not_https["endpoint"] = "ftp://push.test.example/x"
    assert (
        await act_as(world.manager).post("/api/notifications/devices", json=not_https)
    ).status_code in (201, 422)


async def test_a_preference_is_changed_in_parts_and_quiet_hours_come_in_pairs(
    act_as, world, push_on
):
    client = act_as(world.manager)
    start = (await client.get("/api/notifications")).json()["preference"]
    assert start == {
        "push": True,
        "mail_summary": False,
        "tasks": True,
        "overdue": True,
        "decisions": True,
        "quiet_from": "19:00:00",
        "quiet_until": "07:30:00",
        "weekends_quiet": True,
    }
    saved = await client.put(
        "/api/notifications/preference",
        json={"quiet_from": "18:00", "mail_summary": True},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["quiet_from"] == "18:00:00" and saved.json()["tasks"] is True
    assert saved.json()["mail_summary"] is True
    off = await client.put("/api/notifications/preference", json={"quiet": False})
    assert off.json()["quiet_from"] is None and off.json()["quiet_until"] is None
    half = await client.put(
        "/api/notifications/preference", json={"quiet_from": "20:00"}
    )
    assert half.status_code == 422


async def test_a_trial_notification_is_sent_even_in_quiet_hours(
    act_as, world, db_session, push_on
):
    client = act_as(world.manager)
    assert (await client.post("/api/notifications/test")).status_code == 422
    browser = Browser()
    await client.post("/api/notifications/devices", json=browser.as_json())
    assert (await client.post("/api/notifications/test")).status_code == 202
    service = PushService()
    night = datetime(2026, 10, 10, 3, 0, tzinfo=AMSTERDAM).astimezone(UTC)
    assert (
        await outbox.send_due(
            db_session, push_on, service, now=night + timedelta(days=3650)
        )
        == 1
    )
    assert browser.read(service.requests[0][2])["k"] == "test"
    assert time(0) < time(1)
