"""The printable report is named as its part is: Rapport, then Eindrapport."""

import pytest

from grip.services.reports.document import render_report_html


def _render(status: str, final_report: dict[str, str] | None = None) -> str:
    return render_report_html(
        {
            "name": "Opdracht Alfa",
            "audience": "internal",
            "status": status,
            "final_report": final_report,
        },
        instance_name="DigiGilde",
    )


def test_a_running_assignment_has_a_report_not_a_final_one() -> None:
    html = _render("in_progress")
    assert "<h1>Rapport</h1>" in html
    assert "<title>Rapport Opdracht Alfa</title>" in html


@pytest.mark.parametrize("status", ["completed", "accounted"])
def test_the_report_is_final_once_the_work_is_done(status: str) -> None:
    html = _render(status)
    assert "<h1>Eindrapport</h1>" in html
    assert "<title>Eindrapport Opdracht Alfa</title>" in html


def test_an_issued_final_report_makes_it_final_whatever_the_status() -> None:
    assert "<h1>Eindrapport</h1>" in _render("in_progress", {"issued_at": "2026-11-01"})
