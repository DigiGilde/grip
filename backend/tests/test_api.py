"""Health, auth status, instance and CSRF through the HTTP layer."""

from grip.core.auth import DEV_PERSON_COOKIE
from grip.middleware.csrf import CSRF_COOKIE_NAME


async def test_health_is_public_and_needs_no_database(_test_app):
    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(
        transport=ASGITransport(app=_test_app), base_url="http://test"
    ) as ac:
        resp = await ac.get("/api/health/")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    assert resp.headers["x-content-type-options"] == "nosniff"


async def test_status_without_any_person(client):
    resp = await client.get("/api/auth/status")
    assert resp.status_code == 200
    assert resp.json() == {
        "authenticated": False,
        "oidc_configured": False,
        "person": None,
        "functions": [],
        "relations": [],
        "guest": None,
        "passkey_login": False,
        "passkey_session": False,
    }


async def test_status_runs_as_first_beheerder_in_dev_mode(client, create_person):
    await create_person("lezer@example.org", functions=["lezer"])
    beheerder = await create_person(
        "beheerder@example.org", name="Beheerder", functions=["beheerder", "planner"]
    )

    body = (await client.get("/api/auth/status")).json()

    assert body["authenticated"] is True
    assert body["person"] == {
        "id": str(beheerder.id),
        "name": "Beheerder",
        "email": "beheerder@example.org",
    }
    assert body["functions"] == ["beheerder", "planner"]
    assert body["relations"] == []


async def test_status_names_the_kinds_of_relation_for_the_navigation(
    client, create_person, db_session
):
    """Leading someone shows as a relation; it is a hint, never a grant."""
    lead = await create_person(
        "lead@example.org", name="Leidinggevende", functions=["beheerder"]
    )
    await create_person("report@example.org", name="Medewerker", manager_id=lead.id)
    await db_session.flush()

    body = (await client.get("/api/auth/status")).json()

    assert body["person"]["id"] == str(lead.id)
    assert body["relations"] == ["line_manager"]


async def test_dev_cookie_picks_the_person(client, create_person):
    await create_person("beheerder@example.org", functions=["beheerder"])
    lezer = await create_person("lezer@example.org", functions=["lezer"])

    client.cookies.set(DEV_PERSON_COOKIE, str(lezer.id))
    body = (await client.get("/api/auth/status")).json()

    assert body["person"]["id"] == str(lezer.id)
    assert body["functions"] == ["lezer"]


async def test_inactive_person_is_not_used(client, create_person):
    person = await create_person(
        "weg@example.org", functions=["beheerder"], is_active=False
    )
    client.cookies.set(DEV_PERSON_COOKIE, str(person.id))

    assert (await client.get("/api/auth/status")).json()["authenticated"] is False


async def test_ended_function_does_not_count(client, create_person, db_session):
    from datetime import date, timedelta

    from grip.models.role import PersonRole

    person = await create_person("oud@example.org")
    db_session.add(
        PersonRole(
            person_id=person.id,
            role_id="beheerder",
            start_date=date.today() - timedelta(days=30),
            end_date=date.today() - timedelta(days=1),
        )
    )
    await db_session.flush()
    client.cookies.set(DEV_PERSON_COOKIE, str(person.id))

    assert (await client.get("/api/auth/status")).json()["functions"] == []


async def test_instance_is_public_and_returns_only_name_and_base_uri(client):
    """The login page shows the instance name, so no person is needed."""
    resp = await client.get("/api/instance")
    assert resp.status_code == 200
    assert resp.json() == {
        "name": "Grip (lokaal)",
        "base_uri": "http://localhost:8010",
    }


async def test_login_without_oidc_is_not_implemented(client):
    assert (await client.get("/api/auth/login")).status_code == 501


async def test_logout_without_oidc_redirects_to_frontend(client):
    resp = await client.get("/api/auth/logout")
    assert resp.status_code == 302
    assert resp.headers["location"] == "http://localhost:5183"


async def test_csrf_cookie_is_set_and_enforced(client, _test_app):
    from httpx import ASGITransport, AsyncClient

    token = client.cookies.get(CSRF_COOKIE_NAME)
    assert token

    # No route accepts POST yet, so a valid token reaches routing (405) and
    # a missing or wrong one is stopped before that (403).
    ok = await client.post("/api/instance")
    assert ok.status_code == 405

    # A second client on the same session, without the fixture's hook that
    # adds the header.
    async with AsyncClient(
        transport=ASGITransport(app=_test_app),
        base_url="http://test",
        cookies=client.cookies,
    ) as bare:
        missing = await bare.post("/api/instance")
        wrong = await bare.post("/api/instance", headers={"X-CSRF-Token": "nope"})

    for resp in (missing, wrong):
        assert resp.status_code == 403
        assert resp.json() == {"detail": "CSRF-token ontbreekt of is ongeldig"}
