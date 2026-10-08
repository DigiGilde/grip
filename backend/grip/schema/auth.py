from uuid import UUID

from pydantic import BaseModel, ConfigDict


class PersonSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    email: str


class AuthStatus(BaseModel):
    authenticated: bool
    oidc_configured: bool
    person: PersonSummary | None = None
    functions: list[str] = []
