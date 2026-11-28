"""Example datasets besides the default one in ``grip.dev.seed``.

A dataset is a module here with ``async def fill(db, settings) -> SeedResult``.
``grip.dev.seed.seed`` guards, empties and dispatches; the module only adds.
``chain`` is no dataset: it describes the example instances and the
assignments between them, for the datasets of both sides.
"""

NAMES: tuple[str, ...] = ("programma", "bzk", "gdi", "odi", "ezk", "nldd")
