"""Every request through a test client proves the chronicle.

A request that writes a read model without a fact is a problem, and so is a case
whose rows no longer say what its chronicle says once the request is done. A test
that arranged rows by hand has tainted its session; its chronicles are no longer
compared, while what a request writes around the chronicle still counts.

``GRIP_RECONSTRUCTION`` selects what happens: ``verify`` (the default) fails the
test, ``report`` appends the problems to the file in ``GRIP_RECONSTRUCTION_REPORT``,
``off`` follows nothing.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession

from grip.chronicle import guard, verify

VERIFY = "verify"
REPORT = "report"
OFF = "off"


def mode() -> str:
    return os.environ.get("GRIP_RECONSTRUCTION", VERIFY)


class Proof:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.problems: list[str] = []
        self.requests = 0
        self.cases_compared = 0

    @asynccontextmanager
    async def following(self, label: str) -> AsyncIterator[None]:
        """One request. What the test arranged before it is not the request's."""
        if mode() == OFF:
            yield
            return
        await self.session.flush()
        with guard.in_request(self.session) as unit:
            yield
            # In production the request commits here.
            await self.session.flush()
        self.requests += 1
        self.problems.extend(f"{label}: {finding}" for finding in unit.findings)
        if guard.tainted(self.session):
            return
        for case in sorted(unit.cases, key=str):
            report = await verify.differences(self.session, case)
            if report.checked:
                self.cases_compared += 1
            self.problems.extend(f"{label}: {item}" for item in report.differences)

    def conclude(self, test: str) -> None:
        unique = list(dict.fromkeys(self.problems))
        if mode() == REPORT:
            with open(os.environ["GRIP_RECONSTRUCTION_REPORT"], "a") as out:
                out.write(
                    f"{test} :: followed {self.requests} requests, compared "
                    f"{self.cases_compared} cases, "
                    f"tainted {guard.tainted(self.session)}\n"
                )
                out.writelines(f"{test} :: PROBLEM {line}\n" for line in unique)
        elif unique:
            raise AssertionError("around the chronicle: " + "; ".join(unique))
