from uuid import UUID

from pydantic import BaseModel, ConfigDict


class PersonSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    email: str


class GuestSummary(BaseModel):
    """An invited signer without a person record in this instance."""

    name: str
    email: str


class AuthStatus(BaseModel):
    # True only for a person of this instance. A guest is not authenticated
    # for the application: ``guest`` is set instead and only the signing
    # pages are open to them.
    authenticated: bool
    oidc_configured: bool
    person: PersonSummary | None = None
    functions: list[str] = []
    # Kinds of relation the person has to anything here: assignment_manager,
    # line_manager, team_member. For the navigation only; no route trusts it.
    relations: list[str] = []
    guest: GuestSummary | None = None
    # Whether a passkey alone can log in here: the login page then offers it.
    passkey_login: bool = False
    # Whether this session began with a passkey instead of the provider.
    passkey_session: bool = False
    # An instance that holds only fictional example data (INSTANCE_MODE).
    example: bool = False
    # The name of who really logged in, when a visitor of an example
    # instance looks as an example person; ``person`` is then that person.
    example_visitor: str | None = None


class ExamplePerson(BaseModel):
    """An example person a visitor of an example instance can look as."""

    id: UUID
    name: str
    functions: list[str] = []


class ExamplePersonChoice(BaseModel):
    person_id: UUID
