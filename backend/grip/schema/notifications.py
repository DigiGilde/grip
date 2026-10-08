from datetime import datetime, time
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DeviceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    label: str
    created_at: datetime
    # When a notification last reached the device.
    last_success_at: datetime | None = None


class PreferenceOut(BaseModel):
    push: bool
    mail_summary: bool
    tasks: bool
    overdue: bool
    decisions: bool
    quiet_from: time | None
    quiet_until: time | None
    weekends_quiet: bool


class PreferenceIn(BaseModel):
    push: bool | None = None
    mail_summary: bool | None = None
    tasks: bool | None = None
    overdue: bool | None = None
    decisions: bool | None = None
    # Both or neither; send ``quiet: false`` to switch quiet hours off.
    quiet_from: time | None = None
    quiet_until: time | None = None
    quiet: bool | None = None
    weekends_quiet: bool | None = None


class NotificationsOut(BaseModel):
    # False where the instance has no key pair: nothing can be sent.
    available: bool
    # The key a browser subscribes for; None when not available.
    public_key: str | None
    daily_cap: int
    # False until the mail summary exists; the choice is kept meanwhile.
    mail_summary_available: bool
    preference: PreferenceOut
    devices: list[DeviceOut]


class DeviceKeysIn(BaseModel):
    p256dh: str = Field(min_length=20, max_length=200)
    auth: str = Field(min_length=8, max_length=100)


class DeviceIn(BaseModel):
    """What ``PushManager.subscribe`` returned for this browser."""

    endpoint: str = Field(min_length=10, max_length=2000)
    keys: DeviceKeysIn
    label: str = Field(default="", max_length=100)
