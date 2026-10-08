"""Outgoing mail: one settings block, one outbox, one way to send.

Without ``SMTP_HOST`` and ``SMTP_FROM`` the feature is off: nothing is
queued, nothing is sent, and every caller behaves as before. A caller
queues a message in the transaction of its own change (``outbox.enqueue``);
the worker sends it (``outbox.run_mail_loop``). Nothing is ever sent from
inside a request.
"""
