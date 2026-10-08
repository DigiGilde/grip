"""Documents on an invoice line: the received invoice itself (data class B)."""

from decimal import Decimal

import pytest
from sqlalchemy import func, select

from grip.models.audit_log import AuditLog
from grip.models.stored_document import StoredDocument
from grip.services import costs, stored_documents

PDF = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< >>\n%%EOF\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 16
XML = b'<?xml version="1.0" encoding="UTF-8"?>\n<Invoice><ID>F-1</ID></Invoice>\n'


@pytest.fixture
async def invoice(db_session, world):
    """A cost item covered by Alfa, with one invoice line."""
    item = await costs.create_cost_item(
        db_session, description="Hostingcontract", actor=world.beheerder
    )
    line = await costs.add_invoice_line(
        db_session,
        item.id,
        kind="actual",
        amount_cents=1000000,
        reference="HOST-26-01",
        actor=world.beheerder,
    )
    await costs.set_coverage(
        db_session, item.id, world.alfa_line.id, Decimal(30), actor=world.beheerder
    )
    return item, line


def _url(item, line, document_id=None):
    base = f"/api/costs/{item.id}/invoice-lines/{line.id}/attachments"
    return f"{base}/{document_id}" if document_id else base


async def _upload(client, item, line, content=PDF, name="factuur.pdf", kind=None):
    return await client.post(
        _url(item, line), files={"file": (name, content, kind or "application/pdf")}
    )


def _line(body, line):
    return next(x for x in body["invoice_lines"] if x["id"] == str(line.id))


async def test_upload_list_download_and_remove(
    client, world, as_person, invoice, db_session
):
    item, line = invoice
    as_person(world.owner)
    resp = await _upload(client, item, line)
    assert resp.status_code == 201
    attachments = _line(resp.json(), line)["attachments"]
    assert len(attachments) == 1
    attachment = attachments[0]
    assert attachment["filename"] == "factuur.pdf"
    assert attachment["content_type"] == "application/pdf"
    assert attachment["size_bytes"] == len(PDF)
    assert attachment["uploaded_by_name"] == "Olga Opdrachteigenaar"

    download = await client.get(_url(item, line, attachment["id"]))
    assert download.status_code == 200
    assert download.content == PDF
    assert download.headers["content-type"] == "application/pdf"
    assert download.headers["content-disposition"].startswith("attachment;")
    assert download.headers["x-content-type-options"] == "nosniff"
    assert "sandbox" in download.headers["content-security-policy"]

    removed = await client.delete(_url(item, line, attachment["id"]))
    assert removed.status_code == 200
    assert _line(removed.json(), line)["attachments"] == []
    # The file itself is gone, not only the link to it.
    left = await db_session.scalar(select(func.count()).select_from(StoredDocument))
    assert left == 0
    assert (await client.get(_url(item, line, attachment["id"]))).status_code == 404

    rows = (
        await db_session.execute(
            select(AuditLog).where(AuditLog.entity == "invoice_attachment")
        )
    ).scalars()
    actions = sorted(row.action for row in rows)
    assert actions == ["create", "delete"]


async def test_several_files_on_one_line(client, world, as_person, invoice):
    item, line = invoice
    as_person(world.owner)
    await _upload(client, item, line, PDF, "factuur.pdf")
    resp = await _upload(client, item, line, PNG, "scan.png", "image/png")
    names = [a["filename"] for a in _line(resp.json(), line)["attachments"]]
    assert sorted(names) == ["factuur.pdf", "scan.png"]


@pytest.mark.parametrize(
    ("content", "name", "declared", "stored"),
    [
        (PDF, "factuur.pdf", "application/pdf", "application/pdf"),
        (PNG, "scan.png", "image/png", "image/png"),
        (JPEG, "foto.jpg", "image/jpeg", "image/jpeg"),
        (XML, "e-factuur.xml", "application/xml", "application/xml"),
        (XML, "e-factuur.xml", "text/xml", "application/xml"),
    ],
)
async def test_accepted_types(
    client, world, as_person, invoice, content, name, declared, stored
):
    item, line = invoice
    as_person(world.owner)
    resp = await _upload(client, item, line, content, name, declared)
    assert resp.status_code == 201
    assert _line(resp.json(), line)["attachments"][0]["content_type"] == stored


@pytest.mark.parametrize(
    ("content", "name", "declared"),
    [
        # The declared type alone is not trusted.
        (b"MZ\x90\x00 not a pdf", "factuur.pdf", "application/pdf"),
        (PDF, "scan.png", "image/png"),
        (b"<html><script>alert(1)</script></html>", "e-factuur.xml", "text/xml"),
        (b"<!DOCTYPE html><html></html>", "e-factuur.xml", "application/xml"),
        # Types that are not an invoice.
        (b"<svg xmlns='http://www.w3.org/2000/svg'/>", "plaatje.svg", "image/svg+xml"),
        (b"<html></html>", "pagina.html", "text/html"),
        (b"PK\x03\x04", "map.zip", "application/zip"),
        (b"", "leeg.pdf", "application/pdf"),
    ],
)
async def test_refused_files(
    client, world, as_person, invoice, db_session, content, name, declared
):
    item, line = invoice
    as_person(world.owner)
    resp = await _upload(client, item, line, content, name, declared)
    assert resp.status_code == 422
    left = await db_session.scalar(select(func.count()).select_from(StoredDocument))
    assert left == 0


async def test_too_large_is_refused(client, world, as_person, invoice, monkeypatch):
    item, line = invoice
    monkeypatch.setattr(stored_documents, "MAX_DOCUMENT_BYTES", 64)
    as_person(world.owner)
    resp = await _upload(client, item, line, PDF + b"x" * 64)
    assert resp.status_code == 422
    assert "te groot" in resp.json()["detail"]


@pytest.mark.parametrize(
    ("given", "stored"),
    [
        ("../../etc/passwd.pdf", "passwd.pdf"),
        ("C:\\Users\\iemand\\factuur.pdf", "factuur.pdf"),
        ("fac<tuur>;.pdf", "factuur.pdf"),
        (".verborgen.pdf", "verborgen.pdf"),
        ("factuur maart 2026.pdf", "factuur maart 2026.pdf"),
    ],
)
async def test_file_name_is_sanitised(client, world, as_person, invoice, given, stored):
    item, line = invoice
    as_person(world.owner)
    resp = await _upload(client, item, line, PDF, given)
    assert _line(resp.json(), line)["attachments"][0]["filename"] == stored


async def test_access_follows_the_cost_item(client, world, as_person, invoice):
    item, line = invoice
    as_person(world.owner)
    attachment = _line((await _upload(client, item, line)).json(), line)["attachments"][
        0
    ]

    # A reader of class B may download, not upload or remove.
    as_person(world.lezer)
    assert (await client.get(_url(item, line, attachment["id"]))).status_code == 200
    assert (await _upload(client, item, line)).status_code == 403
    assert (await client.delete(_url(item, line, attachment["id"]))).status_code == 403

    # Whoever may not see the cost item learns nothing about its files.
    for person in (world.planner, world.hired, world.outsider):
        as_person(person)
        assert (await client.get(_url(item, line, attachment["id"]))).status_code == 404
        assert (await _upload(client, item, line)).status_code == 404
        assert (
            await client.delete(_url(item, line, attachment["id"]))
        ).status_code == 404


async def test_a_file_is_only_reachable_through_its_own_line(
    client, world, as_person, invoice, db_session
):
    item, line = invoice
    other = await costs.add_invoice_line(
        db_session, item.id, kind="estimate", amount_cents=1, actor=world.beheerder
    )
    as_person(world.owner)
    attachment = _line((await _upload(client, item, line)).json(), line)["attachments"][
        0
    ]
    assert (await client.get(_url(item, other, attachment["id"]))).status_code == 404
    assert (await client.delete(_url(item, other, attachment["id"]))).status_code == 404
    zero = "00000000-0000-0000-0000-000000000000"
    assert (await client.get(_url(item, line, zero))).status_code == 404


async def test_deleting_a_line_deletes_its_files(
    client, world, as_person, invoice, db_session
):
    item, line = invoice
    as_person(world.owner)
    await _upload(client, item, line)
    resp = await client.delete(f"/api/costs/{item.id}/invoice-lines/{line.id}")
    assert resp.status_code == 200 and resp.json()["invoice_lines"] == []
    left = await db_session.scalar(select(func.count()).select_from(StoredDocument))
    assert left == 0


async def test_adding_a_line_tells_which_line_it_made(
    client, world, as_person, invoice
):
    item, _line_ = invoice
    as_person(world.owner)
    resp = await client.post(
        f"/api/costs/{item.id}/invoice-lines",
        json={"kind": "estimate", "amount_cents": 250000, "reference": "HOST-26-02"},
    )
    assert resp.status_code == 201
    body = resp.json()
    created = next(
        x for x in body["invoice_lines"] if x["id"] == body["created_invoice_line_id"]
    )
    assert created["reference"] == "HOST-26-02" and created["attachments"] == []


async def test_a_line_can_be_corrected(client, world, as_person, invoice, db_session):
    item, line = invoice
    as_person(world.owner)
    resp = await client.patch(
        f"/api/costs/{item.id}/invoice-lines/{line.id}",
        json={"amount_cents": 1050000, "period": "2026-03-01", "reference": None},
    )
    assert resp.status_code == 200
    changed = _line(resp.json(), line)
    assert changed["amount_cents"] == 1050000
    assert changed["period"] == "2026-03-01"
    assert changed["reference"] is None
    assert changed["kind"] == "actual"
    assert resp.json()["forecast_cents"] == 1050000

    row = (
        await db_session.execute(
            select(AuditLog).where(
                AuditLog.entity == "invoice_line", AuditLog.action == "update"
            )
        )
    ).scalar_one()
    assert row.old_value["amount_cents"] == 1000000
    assert row.new_value["amount_cents"] == 1050000

    as_person(world.lezer)
    resp = await client.patch(
        f"/api/costs/{item.id}/invoice-lines/{line.id}", json={"amount_cents": 1}
    )
    assert resp.status_code == 403
