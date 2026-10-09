"""Two people on one budget line: the second save is refused, with who and when.

All names are fictional.
"""

from __future__ import annotations


def _line(budget: dict, line_id) -> dict:
    return next(line for line in budget["lines"] if line["id"] == str(line_id))


async def test_the_second_save_on_a_budget_line_is_refused(client, world, as_person):
    as_person(world.owner)
    url = f"/api/budget-lines/{world.line.id}"
    # A fresh line starts at version 1; the first read of it says so.
    opened = {"version": world.line.version}
    started_from = opened["version"]
    header = {"If-Match": f'"{world.line.id}:{started_from}"'}

    # The first tab saves.
    first = await client.patch(url, json={"fte": "0.5"}, headers=header)
    assert first.status_code == 200, first.text
    assert _line(first.json(), world.line.id)["version"] == started_from + 1

    # The second tab started from the same version: refused, nothing written.
    second = await client.patch(url, json={"fte": "0.6"}, headers=header)
    assert second.status_code == 409, second.text
    problem = second.json()
    assert problem["code"] == "StaleWriteError"
    assert "deze begrotingsregel intussen gewijzigd" in problem["detail"]
    assert "changed_by" in problem and "changed_at" in problem
    assert problem["changed_by"] == world.owner.name

    # On top of what stands there now it goes through.
    again = await client.patch(
        url,
        json={"fte": "0.6"},
        headers={"If-Match": f'"{world.line.id}:{started_from + 1}"'},
    )
    assert again.status_code == 200, again.text
    assert _line(again.json(), world.line.id)["fte"] in ("0.6", "0.600")

    # A save without the header is not checked.
    plain = await client.patch(url, json={"fte": "0.7"})
    assert plain.status_code == 200, plain.text
