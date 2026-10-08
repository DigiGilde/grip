from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PasskeyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    label: str
    created_at: datetime
    last_used_at: datetime | None = None
    # "single_device" or "multi_device" (synced by the platform's keychain).
    device_type: str | None = None
    backed_up: bool | None = None


class PasskeyListOut(BaseModel):
    # False when the instance has no relying party configured.
    available: bool
    # Whether a passkey alone can log in here, and for how many days after
    # the last login through the identity provider.
    login_enabled: bool
    login_max_age_days: int
    # Registering needs a session that began at the identity provider.
    may_register: bool
    items: list[PasskeyOut]


class OptionsOut(BaseModel):
    # The options for navigator.credentials, as the JSON the browser parses.
    options_json: str


class RegisterIn(BaseModel):
    # What navigator.credentials.create returned, as JSON.
    credential: str = Field(max_length=20000)
    label: str = Field(default="Passkey", max_length=100)


class AssertionIn(BaseModel):
    # What navigator.credentials.get returned, as JSON.
    credential: str = Field(max_length=20000)
