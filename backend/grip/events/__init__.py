"""The event stream: one durable record of what happened in the instance.

- ``stream``: the one way to write an event, and the handlers that react.
- ``chain``: the hash chain and its check.
- ``classification``: the data class of every event and field.
- ``reading``: the stream as an audit log for people, through the access
  model.
- ``cloudevents`` and ``logboek``: the stream as other systems read it.
"""
