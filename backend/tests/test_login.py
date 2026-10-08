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
