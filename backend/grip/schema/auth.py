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
    guest: GuestSummary | None = None
