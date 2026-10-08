"""The audit log: the change records of the event stream.

There is one record of what happened (``grip.models.stream_event``). This
name stays for the code that asks "who changed this entity, and when".
"""

from grip.models.stream_event import AuditLog

__all__ = ["AuditLog"]
