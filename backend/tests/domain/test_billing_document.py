"""The delivery document: what it calls itself and how it adds up per month."""

from __future__ import annotations

from typing import Any

from grip.services.billing_document import render_html
from grip.services.quote_document import Letterhead


def _line(month: str, label: str, amount: int, *, correction: bool = False) -> dict:
    return {
        "month": month,
        "month_label": label,
        "description": "Naverrekening Developer" if correction else "Developer",
        "person_name": "",
        "fte_pct": "100",
        "monthly_rate_cents": 1250000,
        "amount_cents": amount,
        "correction": correction,
    }


def _content(lines: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "delivered_at": "2026-04-02T09:00:00+00:00",
        "delivered_by_name": None,
        "sender": "Voorbeeldgilde",
        "details": {
            "organisation": "Voorbeeldministerie",
            "address": "Postbus 1",
            "postcode_city": "1000 AA Voorbeeldstad",
            "reference": "VM-2026-118",
        },
        "assignment_name": "Opdracht Alfa",
        "client_name": "Voorbeeldministerie",
        "period_label": "eerste kwartaal 2026",
        "rhythm": "quarter",
        "lines": lines,
        "total_cents": sum(line["amount_cents"] for line in lines),
        "reference": "VG-F-2026-0001",
        "assignment_uri": "https://grip.example/id/opdracht/1",
        "with_names": False,
    }


def test_a_period_gets_a_subtotal_per_month() -> None:
    html = render_html(
        _content(
            [
                _line("2026-01", "januari 2026", 1250000),
                _line("2026-01", "januari 2026", 900000),
                _line("2026-02", "februari 2026", 1250000),
                _line("2026-02", "februari 2026", 900000),
            ]
        ),
        Letterhead(),
    )
    assert "<h1>Factuurverzoek</h1>" in html
    assert "Te factureren over eerste kwartaal 2026" in html
    assert html.count("Subtotaal januari 2026") == 1
    assert html.count("Subtotaal februari 2026") == 1
    assert "21.500,00" in html.replace("\xa0", " ")


def test_one_line_per_month_needs_no_subtotal() -> None:
    html = render_html(
        _content(
            [
                _line("2026-01", "januari 2026", 1250000),
                _line("2026-02", "februari 2026", 1250000),
            ]
        ),
        Letterhead(),
    )
    assert "Subtotaal" not in html


def test_only_differences_make_it_a_naverrekening() -> None:
    """A document with nothing but corrections does not pose as a period
    that is delivered for the first time."""
    html = render_html(
        _content(
            [
                _line("2026-02", "februari 2026", 250000, correction=True),
                _line("2026-03", "maart 2026", 250000, correction=True),
            ]
        ),
        Letterhead(),
    )
    assert "<h1>Naverrekening</h1>" in html
    assert "<title>Naverrekening VG-F-2026-0001</title>" in html
    assert "Na te verrekenen over eerste kwartaal 2026" in html
    assert "Te factureren over" not in html
    assert "bovenop wat eerder over de periode is aangeleverd" in html


def test_a_month_delivered_again_names_the_request_it_replaces() -> None:
    content = _content([_line("2026-02", "februari 2026", 2965000)])
    content["replaces"] = [
        {
            "month_label": "februari 2026",
            "reference": "VG-F-2026-0001/2026-Q1",
            "amount_cents": 3290000,
            "difference_cents": -325000,
        }
    ]
    html = render_html(content, Letterhead())
    assert "Dit verzoek vervangt februari 2026 uit factuurverzoek" in html
    assert "VG-F-2026-0001/2026-Q1" in html
    assert "Het verschil is -€ 3.250,00." in html
    # A first delivery replaces nothing and says nothing about it.
    assert "vervangt" not in render_html(
        _content([_line("2026-02", "februari 2026", 2965000)]), Letterhead()
    )
