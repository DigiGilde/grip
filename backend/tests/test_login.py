"""Access is pre-provisioned: who may log in, and how the subject is bound."""

from sqlalchemy import select

from grip.core.auth import resolve_person_for_login
from grip.models.audit_log import AuditLog


async def test_unknown_identity_gets_no_access_and_no_person(db_session):
    from grip.models.person import Person

    person = await resolve_person_for_login(
        db_session, sub="sub-1", email="vreemd@example.org", email_verified=True
    )
    assert person is None
    assert (await db_session.execute(select(Person))).scalars().all() == []


async def test_first_login_binds_subject_on_verified_email(db_session, create_person):
    provisioned = await create_person("Nieuw@Example.org", name="Nieuw@Example.org")

    person = await resolve_person_for_login(
        db_session,
        sub="sub-1",
        email="nieuw@example.ORG",
        email_verified=True,
        name="Nieuwe Collega",
    )

    assert person is not None and person.id == provisioned.id
    assert person.oidc_subject == "sub-1"
    assert person.name == "Nieuwe Collega"

    audit = (await db_session.execute(select(AuditLog))).scalars().one()
    assert audit.entity == "person" and audit.entity_id == str(person.id)
    assert audit.old_value == {"oidc_subject": None}
    assert audit.new_value == {"oidc_subject": "sub-1"}


async def test_given_name_is_kept_on_first_login(db_session, create_person):
    await create_person("a@example.org", name="Ingevoerde Naam")
    person = await resolve_person_for_login(
        db_session, sub="s", email="a@example.org", email_verified=True, name="IdP"
    )
    assert person is not None and person.name == "Ingevoerde Naam"


async def test_unverified_email_does_not_bind(db_session, create_person):
    provisioned = await create_person("a@example.org")
    person = await resolve_person_for_login(
        db_session, sub="sub-1", email="a@example.org", email_verified=False
    )
    assert person is None
    assert provisioned.oidc_subject is None


async def test_bound_person_is_matched_on_subject_not_email(db_session, create_person):
    bound = await create_person("oud@example.org", oidc_subject="sub-1")
    person = await resolve_person_for_login(
        db_session, sub="sub-1", email="nieuw-adres@example.org", email_verified=False
    )
    assert person is not None and person.id == bound.id


async def test_email_of_bound_person_cannot_be_taken_over(db_session, create_person):
    """Another subject with the same verified email must not get in."""
    bound = await create_person("a@example.org", oidc_subject="sub-1")
    person = await resolve_person_for_login(
        db_session, sub="sub-2", email="a@example.org", email_verified=True
    )
    assert person is None
    assert bound.oidc_subject == "sub-1"


async def test_inactive_person_is_refused(db_session, create_person):
    await create_person("bound@example.org", oidc_subject="sub-1", is_active=False)
    await create_person("unbound@example.org", is_active=False)

    assert (
        await resolve_person_for_login(
            db_session, sub="sub-1", email="bound@example.org", email_verified=True
        )
        is None
    )
    assert (
        await resolve_person_for_login(
            db_session, sub="sub-2", email="unbound@example.org", email_verified=True
        )
        is None
    )


async def test_missing_subject_is_refused(db_session, create_person):
    await create_person("a@example.org")
    assert (
        await resolve_person_for_login(
            db_session, sub="", email="a@example.org", email_verified=True
        )
        is None
    )


async def test_another_subject_for_a_bound_person_is_refused_and_logged(
    db_session, create_person, caplog
):
    """The provider was recreated, or the person got a new account there."""
    import logging

    person = await create_person("gebonden@example.org", name="Gebonden Persoon")
    person.oidc_subject = "sub-oud"
    await db_session.flush()

    with caplog.at_level(logging.INFO, logger="grip.core.auth"):
        result = await resolve_person_for_login(
            db_session,
            sub="sub-nieuw",
            email="gebonden@example.org",
            email_verified=True,
        )

    assert result is None
    assert person.oidc_subject == "sub-oud"
    records = [r for r in caplog.records if "bound to another subject" in r.message]
    assert len(records) == 1
    assert records[0].levelno == logging.WARNING
    assert str(person.id) in records[0].getMessage()
    # Who it is follows from the id; the address and the subjects stay out.
    logged = " ".join(r.getMessage() for r in caplog.records)
    assert "gebonden@example.org" not in logged
    assert "sub-oud" not in logged and "sub-nieuw" not in logged


async def test_unbinding_lets_the_next_login_bind_again(db_session, create_person):
    from grip.services import team

    beheerder = await create_person("beheer@example.org", functions=["beheerder"])
    person = await create_person("gebonden@example.org", name="Gebonden Persoon")
    person.oidc_subject = "sub-oud"
    await db_session.flush()

    await team.unbind_login(db_session, person.id, actor=beheerder)
    assert person.oidc_subject is None

    audit = (
        (
            await db_session.execute(
                select(AuditLog).where(AuditLog.entity_id == str(person.id))
            )
        )
        .scalars()
        .all()
    )
    assert [(a.old_value, a.new_value) for a in audit] == [
        ({"login_bound": True}, {"login_bound": False})
    ]
    assert "sub-oud" not in str([(a.old_value, a.new_value) for a in audit])

    again = await resolve_person_for_login(
        db_session, sub="sub-nieuw", email="gebonden@example.org", email_verified=True
    )
    assert again is not None and again.id == person.id
    assert person.oidc_subject == "sub-nieuw"


async def test_unbinding_someone_who_never_logged_in_is_refused(
    db_session, create_person
):
    import pytest

    from grip.services import team
    from grip.services.errors import DomainValidationError

    person = await create_person("nieuw@example.org")
    with pytest.raises(DomainValidationError):
        await team.unbind_login(db_session, person.id, actor=None)
