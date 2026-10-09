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


def _stated(amount: int, **more: Any) -> dict[str, Any]:
    return {
        "month": "2026-03",
        "month_label": "maart 2026",
        "amount_cents": amount,
        "cause": "inzetschaal gewijzigd met ingang van 1 maart 2026",
        "follows_reference": "O-12/2026-Q1",
        "follows_delivered_on": "2026-04-02",
        **more,
    }


def test_a_naverrekening_says_why_and_on_top_of_which_request() -> None:
    content = _content([_line("2026-03", "maart 2026", 250000, correction=True)])
    content["corrections"] = [_stated(250000)]
    html = " ".join(render_html(content, Letterhead()).split())
    assert "Naverrekening maart 2026: € 2.500,00." in html
    assert "Inzetschaal gewijzigd met ingang van 1 maart 2026." in html
    assert "Dit bedrag komt bovenop factuurverzoek" in html
    assert "O-12/2026-Q1</span> van 2 april 2026." in html


def test_a_negative_naverrekening_comes_off_the_earlier_request() -> None:
    content = _content([_line("2026-03", "maart 2026", -240000, correction=True)])
    content["corrections"] = [_stated(-240000)]
    html = " ".join(render_html(content, Letterhead()).split())
    assert "Dit bedrag gaat af van factuurverzoek" in html
    assert "komt bovenop factuurverzoek" not in html


def test_a_naverrekening_without_a_known_request_still_says_what_to_do() -> None:
    content = _content([_line("2026-03", "maart 2026", 250000, correction=True)])
    content["corrections"] = [
        _stated(250000, follows_reference=None, follows_delivered_on=None, cause="")
    ]
    html = " ".join(render_html(content, Letterhead()).split())
    assert (
        "Naverrekening maart 2026: € 2.500,00. Dit bedrag komt bovenop wat eerder "
        "over deze maand is aangeleverd." in html
    )


def test_a_request_without_differences_says_nothing_about_them() -> None:
    html = render_html(
        _content([_line("2026-01", "januari 2026", 1250000)]), Letterhead()
    )
    assert (
        "Naverrekening januari" not in html
        and "komt bovenop factuurverzoek" not in html
    )


def test_a_quarter_with_three_roles_fits_one_page() -> None:
    """Three months of three roles, with subtotals, the total and the closing
    lines: one page, at the type size the document always has."""
    from grip.services.quote_document import (
        DocumentEngineError,
        _find_homebrew_libraries,
    )

    _find_homebrew_libraries()
    try:
        from weasyprint import HTML
    except (OSError, ImportError) as exc:  # pragma: no cover - no engine here
        import pytest

        pytest.skip(f"geen pdf-motor: {DocumentEngineError.__name__} ({exc})")

    def role(month: str, label: str, name: str, amount: int) -> dict:
        return {**_line(month, label, amount), "description": name}

    months = [
        ("2026-01", "januari 2026"),
        ("2026-02", "februari 2026"),
        ("2026-03", "maart 2026"),
    ]
    lines = [
        role(month, label, name, amount)
        for month, label in months
        for name, amount in (
            ("Developer", 1250000),
            ("Ontwerper", 900000),
            ("Productmanager", 1440000),
        )
    ]
    content = _content(lines)
    content["delivered_by_name"] = "Voorbeeld Een"
    html = render_html(content, Letterhead())
    assert len(HTML(string=html).render().pages) == 1
    # By spacing, not by a smaller letter.
    assert "font-size: 8.5pt" in html


def test_a_billing_request_from_an_example_instance_says_so() -> None:
    content = _content([_line("2026-01", "januari 2026", 1250000)])
    assert "Voorbeeld, geen echt document" in render_html(
        content, Letterhead(example=True)
    )
    assert "geen echt document" not in render_html(content, Letterhead())
