"""The first beheerder comes from BOOTSTRAP_BEHEERDER_EMAILS."""

from sqlalchemy import func, select

from grip.core.bootstrap import DEV_BEHEERDER_EMAIL, bootstrap_beheerders
from grip.core.config import Settings
from grip.models.audit_log import AuditLog
from grip.models.person import Person
from grip.models.role import PersonRole
from grip.repositories.person import PersonRepository


def _settings(**overrides) -> Settings:
    return Settings(_env_file=None, DEV_NO_AUTH=True, **overrides)


async def _count(db, model) -> int:
    return (await db.execute(select(func.count()).select_from(model))).scalar_one()


async def test_creates_person_with_beheerder_and_audit(db_session):
    settings = _settings(BOOTSTRAP_BEHEERDER_EMAILS="Eerste@Example.org")

    (person,) = await bootstrap_beheerders(db_session, settings)

    assert person.email == "eerste@example.org"
    assert person.is_active and person.oidc_subject is None
    repo = PersonRepository(db_session)
    assert await repo.active_function_ids(person.id) == ["beheerder"]
    assert await _count(db_session, AuditLog) == 2


async def test_is_idempotent(db_session):
    settings = _settings(BOOTSTRAP_BEHEERDER_EMAILS="a@example.org,b@example.org")

    await bootstrap_beheerders(db_session, settings)
    await bootstrap_beheerders(db_session, settings)

    assert await _count(db_session, Person) == 2
    assert await _count(db_session, PersonRole) == 2


async def test_existing_person_only_gets_the_function(db_session, create_person):
    existing = await create_person(
        "a@example.org", name="Bestaand", functions=["lezer"]
    )

    (person,) = await bootstrap_beheerders(
        db_session, _settings(BOOTSTRAP_BEHEERDER_EMAILS="A@example.org")
    )

    assert person.id == existing.id and person.name == "Bestaand"
    repo = PersonRepository(db_session)
    assert await repo.active_function_ids(person.id) == ["beheerder", "lezer"]


async def test_dev_mode_without_emails_creates_a_stand_in(db_session):
    (person,) = await bootstrap_beheerders(db_session, _settings())
    assert person.email == DEV_BEHEERDER_EMAIL


async def test_no_stand_in_with_oidc(db_session):
    settings = Settings(
        _env_file=None,
        DEV_NO_AUTH=False,
        OIDC_ISSUER="https://idp.example/realms/x",
        SESSION_SECRET_KEY="s" * 40,
    )
    assert await bootstrap_beheerders(db_session, settings) == []
    assert await _count(db_session, Person) == 0
