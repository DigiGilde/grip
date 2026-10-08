"""Quote routes: preview, issue, list, document, invitations, uploaded pdf."""

from tests.api.quotes.conftest import PDF_BYTES

# 0.8 FTE in category D for all of 2026: 0.8 x 12 x 18,000.
BUDGET_CENTS = 17_280_000


async def _issue(act_as, world) -> dict:
    client = act_as(world.manager)
    response = await client.post(
        f"/api/assignments/{world.assignment.id}/quotes",
        json={"valid_until": "2026-03-31", "conditions": "Betaling per maand."},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_preview_adds_up_to_the_budget(act_as, world):
    client = act_as(world.manager)
    response = await client.get(f"/api/assignments/{world.assignment.id}/quote-preview")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["can_issue"] is True
    assert body["content"]["total_cents"] == BUDGET_CENTS
    line = body["content"]["lines"][0]
    assert line["description"] == "Productmanager"
    assert line["fte"] == "0.8"
    assert line["rate_category"] == "D"
    assert line["monthly_rates"] == [{"year": 2026, "monthly_rate_cents": 1_800_000}]
    assert body["content"]["subtotals_per_year"] == [
        {"year": 2026, "amount_cents": BUDGET_CENTS}
    ]
    # No agreed amount yet, so no difference.
    assert body["quoted_amount_cents"] is None
    assert body["difference_cents"] is None


async def test_preview_shows_difference_to_agreed_amount(act_as, world, db_session):
    world.assignment.quoted_amount_cents = 17_000_000
    await db_session.flush()
    client = act_as(world.manager)
    body = (
        await client.get(f"/api/assignments/{world.assignment.id}/quote-preview")
    ).json()
    assert body["difference_cents"] == 17_000_000 - BUDGET_CENTS


async def test_preview_without_money_for_a_planner(act_as, world):
    """A planner reads assignment basics but nothing financial."""
    client = act_as(world.planner)
    response = await client.get(f"/api/assignments/{world.assignment.id}/quote-preview")
    assert response.status_code == 200
    body = response.json()
    assert body["assignment_name"] == "Opdracht Alfa"
    assert "quoted_amount_cents" not in body
    assert "difference_cents" not in body
    # Not even the number of lines.
    assert "content" not in body


async def test_preview_is_hidden_from_an_outsider(act_as, world):
    client = act_as(world.outsider)
    response = await client.get(f"/api/assignments/{world.assignment.id}/quote-preview")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")


async def test_issue_freezes_the_budget(act_as, world, db_session):
    quote = await _issue(act_as, world)
    assert quote["status"] == "issued"
    assert quote["total_cents"] == BUDGET_CENTS
    assert len(quote["snapshot_hash"]) == 64
    assert quote["valid_until"] == "2026-03-31"
    assert quote["content"]["conditions"] == "Betaling per maand."
    assert quote["issued_by_name"] == "Opdracht Manager"

    # A later change to the rate card does not change the issued quote.
    from grip.services import rates

    await rates.set_rate_band(db_session, 2026, "D", 2_000_000, actor=world.beheerder)
    client = act_as(world.manager)
    again = (await client.get(f"/api/quotes/{quote['id']}")).json()
    assert again["total_cents"] == BUDGET_CENTS
    assert again["snapshot_hash"] == quote["snapshot_hash"]
    preview = (
        await client.get(f"/api/assignments/{world.assignment.id}/quote-preview")
    ).json()
    assert preview["content"]["total_cents"] != BUDGET_CENTS


async def test_only_a_manager_issues(act_as, world):
    for person in (world.lezer, world.planner, world.member, world.beheerder):
        client = act_as(person)
        response = await client.post(
            f"/api/assignments/{world.assignment.id}/quotes", json={}
        )
        assert response.status_code == 403, person.email
    client = act_as(world.outsider)
    response = await client.post(
        f"/api/assignments/{world.assignment.id}/quotes", json={}
    )
    assert response.status_code == 403


async def test_list_marks_an_earlier_quote_superseded(act_as, world):
    first = await _issue(act_as, world)
    second = await _issue(act_as, world)
    client = act_as(world.manager)
    body = (await client.get(f"/api/assignments/{world.assignment.id}/quotes")).json()
    by_id = {q["id"]: q for q in body["quotes"]}
    assert by_id[first["id"]]["status"] == "superseded"
    assert by_id[second["id"]]["status"] == "issued"
    assert body["quotes"][0]["id"] == second["id"]


async def test_list_without_financial_fields_for_a_planner(act_as, world):
    quote = await _issue(act_as, world)
    client = act_as(world.planner)
    body = (await client.get(f"/api/assignments/{world.assignment.id}/quotes")).json()
    entry = body["quotes"][0]
    assert entry["id"] == quote["id"]
    assert entry["status"] == "issued"
    for hidden in ("total_cents", "snapshot_hash", "valid_until"):
        assert hidden not in entry


async def test_quote_is_hidden_from_a_member_and_an_outsider(act_as, world):
    quote = await _issue(act_as, world)
    for person in (world.member, world.outsider):
        client = act_as(person)
        assert (await client.get(f"/api/quotes/{quote['id']}")).status_code == 404
        assert (
            await client.get(f"/api/quotes/{quote['id']}/document")
        ).status_code == 404


async def test_document_is_rendered_from_the_snapshot(act_as, world, db_session):
    quote = await _issue(act_as, world)
    world.assignment.name = "Later hernoemd"
    await db_session.flush()
    client = act_as(world.manager)
    response = await client.get(f"/api/quotes/{quote['id']}/document")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "default-src 'none'" in response.headers["content-security-policy"]
    html = response.text
    assert "Opdracht Alfa" in html
    assert "Later hernoemd" not in html
    assert "€ 172.800,00" in html
    assert "Voorbeeldministerie" in html
    assert quote["snapshot_hash"] in html.replace(" ", "")
    assert "Betaling per maand." in html
    assert "<script" not in html

    download = await client.get(f"/api/quotes/{quote['id']}/document?download=true")
    assert download.headers["content-disposition"].startswith("attachment;")


async def test_document_needs_the_financial_class(act_as, world):
    quote = await _issue(act_as, world)
    client = act_as(world.planner)
    response = await client.get(f"/api/quotes/{quote['id']}/document")
    assert response.status_code == 403


async def test_document_escapes_what_the_snapshot_holds(act_as, world, db_session):
    world.line.description = '<img src=x onerror="alert(1)">'
    await db_session.flush()
    quote = await _issue(act_as, world)
    client = act_as(world.manager)
    html = (await client.get(f"/api/quotes/{quote['id']}/document")).text
    assert "<img" not in html
    assert "&lt;img" in html


async def test_invitations_are_for_the_manager(act_as, world):
    quote = await _issue(act_as, world)
    client = act_as(world.manager)
    created = await client.post(
        f"/api/quotes/{quote['id']}/invitations",
        json={"email": "Tekenaar@Opdrachtgever.example"},
    )
    assert created.status_code == 201, created.text
    assert created.json()["email"] == "tekenaar@opdrachtgever.example"
    listed = (await client.get(f"/api/quotes/{quote['id']}/invitations")).json()
    assert [i["email"] for i in listed["invitations"]] == [
        "tekenaar@opdrachtgever.example"
    ]

    # A reader of totals does not learn who was invited.
    client = act_as(world.lezer)
    assert (
        await client.get(f"/api/quotes/{quote['id']}/invitations")
    ).status_code == 403
    assert (
        await client.post(
            f"/api/quotes/{quote['id']}/invitations", json={"email": "x@y.example"}
        )
    ).status_code == 403


async def test_invitation_refuses_a_bad_address(act_as, world):
    quote = await _issue(act_as, world)
    client = act_as(world.manager)
    response = await client.post(
        f"/api/quotes/{quote['id']}/invitations", json={"email": "geen adres"}
    )
    assert response.status_code == 422


async def test_uploaded_pdf_records_the_acceptance(act_as, world):
    quote = await _issue(act_as, world)
    client = act_as(world.manager)
    response = await client.post(
        f"/api/quotes/{quote['id']}/acceptance/uploaded-pdf",
        data={
            "signer_name": "Directeur Voorbeeld",
            "signer_email": "directeur@opdrachtgever.example",
            "signer_function": "Directeur",
        },
        files={"file": ("getekend.pdf", PDF_BYTES, "application/pdf")},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "accepted"
    assert body["acceptance"]["form"] == "uploaded_pdf"
    assert body["acceptance"]["signer_name"] == "Directeur Voorbeeld"
    assert body["acceptance"]["organisation_name"] == "Voorbeeldministerie"
    assert body["acceptance"]["has_document"] is True

    document = await client.get(f"/api/quotes/{quote['id']}/acceptance/document")
    assert document.status_code == 200
    assert document.content == PDF_BYTES
    assert document.headers["content-type"] == "application/pdf"

    assignment = (
        await client.get(f"/api/assignments/{world.assignment.id}/quote-preview")
    ).json()
    assert assignment["assignment_status"] == "accepted"
    assert assignment["can_issue"] is False

    # The signer's name is class B: a planner sees that it was accepted, not by whom.
    client = act_as(world.planner)
    entry = (await client.get(f"/api/quotes/{quote['id']}")).json()
    assert entry["acceptance"] == {
        "form": "uploaded_pdf",
        "signed_at": body["acceptance"]["signed_at"],
    }
    assert (
        await client.get(f"/api/quotes/{quote['id']}/acceptance/document")
    ).status_code == 403


async def test_uploaded_file_must_be_a_pdf(act_as, world):
    quote = await _issue(act_as, world)
    client = act_as(world.manager)
    for content, content_type in (
        (b"<html></html>", "application/pdf"),
        (PDF_BYTES, "text/html"),
        (b"", "application/pdf"),
    ):
        response = await client.post(
            f"/api/quotes/{quote['id']}/acceptance/uploaded-pdf",
            data={"signer_name": "A", "signer_email": "a@b.example"},
            files={"file": ("x.pdf", content, content_type)},
        )
        assert response.status_code == 422, (content, content_type)
    still = (await client.get(f"/api/quotes/{quote['id']}")).json()
    assert still["status"] == "issued"


async def test_uploaded_file_has_a_size_limit(act_as, world, monkeypatch):
    from grip.services import stored_documents

    monkeypatch.setattr(stored_documents, "MAX_DOCUMENT_BYTES", 64)
    quote = await _issue(act_as, world)
    client = act_as(world.manager)
    response = await client.post(
        f"/api/quotes/{quote['id']}/acceptance/uploaded-pdf",
        data={"signer_name": "A", "signer_email": "a@b.example"},
        files={"file": ("x.pdf", PDF_BYTES + b"x" * 100, "application/pdf")},
    )
    assert response.status_code == 422
    assert "te groot" in response.json()["detail"]


async def test_only_a_manager_records_a_decision(act_as, world):
    quote = await _issue(act_as, world)
    for person in (world.lezer, world.planner, world.beheerder):
        client = act_as(person)
        upload = await client.post(
            f"/api/quotes/{quote['id']}/acceptance/uploaded-pdf",
            data={"signer_name": "A", "signer_email": "a@b.example"},
            files={"file": ("x.pdf", PDF_BYTES, "application/pdf")},
        )
        assert upload.status_code == 403, person.email
        rejection = await client.post(
            f"/api/quotes/{quote['id']}/rejection", json={"reason": "x"}
        )
        assert rejection.status_code == 403, person.email


async def test_recorded_rejection(act_as, world):
    quote = await _issue(act_as, world)
    client = act_as(world.manager)
    response = await client.post(
        f"/api/quotes/{quote['id']}/rejection", json={"reason": "Budget ontbreekt"}
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "rejected"
    assert body["rejection"]["reason"] == "Budget ontbreekt"
    # A decided quote cannot be decided again.
    again = await client.post(f"/api/quotes/{quote['id']}/rejection", json={})
    assert again.status_code == 409
