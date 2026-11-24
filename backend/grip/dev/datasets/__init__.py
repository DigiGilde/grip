"""Example datasets besides the default one in ``grip.dev.seed``.

A dataset is a module here with ``async def fill(db, settings) -> SeedResult``.
``grip.dev.seed.seed`` guards, empties and dispatches; the module only adds.
"""

NAMES: tuple[str, ...] = ("programma",)
