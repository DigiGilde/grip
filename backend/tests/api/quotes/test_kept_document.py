"""The file of a quote is laid out once and kept.

What a client reads and signs is a file. It must be the same file on every
day and for every reader, whatever the letterhead or the template has
become since the quote was made.
"""

from __future__ import annotations

import hashlib
import uuid

import pytest
from sqlalchemy import select

from grip.core.config import get_settings
from grip.models.quote import Quote
from grip.models.stored_document import StoredDocument
from grip.services import quote_files, quotes
from grip.services.errors import DomainError
from tests.api.quotes.conftest import document_text


async def _issued(act_as, world) -> dict:
    response = await act_as(world.manager).post(
        f"/api/assignments/{world.assignment.id}/quotes", json={}
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _stored(db_session, quote_id: str) -> Quote:
    quote = await db_session.get(Quote, uuid.UUID(quote_id))
    assert quote is not None
    return quote


async def test_the_file_is_fixed_when_the_quote_is_made(act_as, world, db_session):
    quote = await _stored(db_session, (await _issued(act_as, world))["id"])
    assert quote.document_origin == "issue"
    assert quote.document_fixed_at == quote.issued_at
    assert quote.document_ref is not None

    kept = await quote_files.file_of(db_session, quote)
    assert kept.content.startswith(b"%PDF-")
    # The hash is the hash of the bytes, not of anything else.
    assert kept.sha256 == hashlib.sha256(kept.content).hexdigest()
    assert kept.sha256 == quote.document_sha256
    assert kept.origin_text.startswith("document vastgelegd bij het maken")
    # One file per quote, owned by the quote.
    documents = (
        (
            await db_session.execute(
                select(StoredDocument).where(
                    StoredDocument.owner_kind == "quote",
                    StoredDocument.owner_id == quote.id,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(documents) == 1


async def test_changing_the_letterhead_afterwards_changes_nothing(
    act_as, world, db_session, monkeypatch
):
    quote = await _issued(act_as, world)
    client = act_as(world.manager)
    url = f"/api/quotes/{quote['id']}/document"
    before = await client.get(url)
    assert before.status_code == 200
    stored = await _stored(db_session, quote["id"])
    assert before.headers["x-document-sha256"] == stored.document_sha256
    assert hashlib.sha256(before.content).hexdigest() == stored.document_sha256

    # The instance gets another letterhead and another name: what an
    # administrator changes, or what a server restarted without its
    # settings ends up with.
    settings = get_settings()
    monkeypatch.setattr(settings, "LETTERHEAD_LINES", "Een andere dienst|Ministerie X")
    monkeypatch.setattr(settings, "LETTERHEAD_LOGO_PATH", "")
    monkeypatch.setattr(settings, "DOCUMENT_FONT_DIR", "")
    monkeypatch.setattr(settings, "INSTANCE_NAME", "Een heel andere naam")

    after = await client.get(url)
    download = await client.get(f"{url}?download=true")
    assert after.content == before.content
    assert download.content == before.content
    assert "Een andere dienst" not in document_text(after)

    # The signer and the approver are shown the same bytes.
    await client.post(
        f"/api/quotes/{quote['id']}/invitations", json={"email": world.signer.email}
    )
    signing = await act_as(world.signer).get(
        f"/api/signing/quotes/{quote['id']}/document"
    )
    assert signing.content == before.content

    # A quote made now does get the new letterhead: the change is for new
    # quotes only.
    newer = await _issued(act_as, world)
    fresh = await act_as(world.manager).get(f"/api/quotes/{newer['id']}/document")
    assert fresh.content != before.content
    assert "Een andere dienst" in document_text(fresh)


async def test_a_quote_from_before_files_were_kept_says_so(
    act_as, world, db_session, monkeypatch
):
    quote = await _stored(db_session, (await _issued(act_as, world))["id"])
    # As it was before this change: content and fingerprint, no file.
    await db_session.execute(
        StoredDocument.__table__.delete().where(StoredDocument.owner_id == quote.id)
    )
    quote.document_ref = None
    quote.document_sha256 = None
    quote.document_fixed_at = None
    quote.document_origin = None
    await db_session.flush()

    client = act_as(world.manager)
    url = f"/api/quotes/{quote.id}/document"
    first = await client.get(url)
    assert first.status_code == 200
    await db_session.refresh(quote)
    assert quote.document_origin == "afterwards"
    assert quote.document_fixed_at > quote.issued_at
    kept = await quote_files.file_of(db_session, quote)
    assert "na het maken van de offerte" in kept.origin_text

    # Fixed once: from here on it does not move either.
    monkeypatch.setattr(get_settings(), "LETTERHEAD_LINES", "Een andere dienst")
    assert (await client.get(url)).content == first.content


async def test_catching_up_gives_every_quote_its_file(act_as, world, db_session):
    quote = await _stored(db_session, (await _issued(act_as, world))["id"])
    assert await quote_files.fix_missing(db_session) == 0
    await db_session.execute(
        StoredDocument.__table__.delete().where(StoredDocument.owner_id == quote.id)
    )
    quote.document_ref = None
    quote.document_sha256 = None
    quote.document_fixed_at = None
    quote.document_origin = None
    await db_session.flush()
    assert await quote_files.fix_missing(db_session) == 1
    assert quote.document_origin == "afterwards"
    assert await quote_files.fix_missing(db_session) == 0


async def test_when_the_file_cannot_be_made_the_quote_is_not_made(
    act_as, world, db_session, monkeypatch
):
    def broken(*_args, **_kwargs):
        raise RuntimeError("the lay-out engine fell over")

    monkeypatch.setattr(quote_files, "render_quote_pdf", broken)
    with pytest.raises(DomainError, match="niet gemaakt"):
        async with db_session.begin_nested():
            await quotes.issue_quote(
                db_session, world.assignment.id, actor=world.manager
            )
    # No quote, no file, and the assignment did not move.
    assert (await db_session.execute(select(Quote))).scalars().all() == []
    await db_session.refresh(world.assignment)
    assert world.assignment.status != "quoted"

    response = await act_as(world.manager).post(
        f"/api/assignments/{world.assignment.id}/quotes", json={}
    )
    assert response.status_code == 422
    assert "niet gemaakt" in response.json()["detail"]


async def test_the_origin_of_the_file_is_in_the_quote_response(
    act_as, world, db_session
):
    quote = await _issued(act_as, world)
    stored = await _stored(db_session, quote["id"])
    # Made here, with its file: the hash, and no note.
    assert quote["document_sha256"] == stored.document_sha256
    assert quote["document_origin"] == "issue"
    assert quote["document_fixed_at"] is not None
    assert quote["document_note"] is None

    await act_as(world.manager).post(
        f"/api/quotes/{quote['id']}/invitations", json={"email": world.signer.email}
    )
    shown = (
        await act_as(world.signer).get(f"/api/signing/quotes/{quote['id']}")
    ).json()
    assert shown["document_sha256"] == stored.document_sha256
    assert shown["document_origin"] == "issue" and shown["document_note"] is None

    # A quote whose file was fixed later says so, to both readers.
    stored.document_origin = "afterwards"
    await db_session.flush()
    url = f"/api/quotes/{quote['id']}"
    later = (await act_as(world.manager).get(url)).json()
    assert later["document_origin"] == "afterwards"
    assert later["document_note"].startswith("vastgelegd na het maken, op ")
    shown = (
        await act_as(world.signer).get(f"/api/signing/quotes/{quote['id']}")
    ).json()
    assert shown["document_note"].startswith("vastgelegd na het maken, op ")

    stored.document_origin = "received"
    await db_session.flush()
    received = (await act_as(world.manager).get(url)).json()
    assert received["document_note"].startswith("eigen opmaak van deze instantie")

    # Class B, like the fingerprint: a reader without it gets none of them.
    for person in (world.planner, world.member):
        seen = await act_as(person).get(url)
        if seen.status_code != 200:
            continue
        for name in (
            "document_sha256",
            "document_fixed_at",
            "document_origin",
            "document_note",
            "snapshot_hash",
        ):
            assert name not in seen.json(), (person.name, name)


def test_the_note_is_only_for_a_file_that_was_not_fixed_at_making():
    from datetime import UTC, datetime

    from grip.schema.quotes import document_note

    day = datetime(2026, 10, 8, tzinfo=UTC)
    assert document_note("issue", day) is None
    assert document_note(None, None) is None
    assert document_note("afterwards", day) == "vastgelegd na het maken, op 08-10-2026"
    assert document_note("received", day) == (
        "eigen opmaak van deze instantie, op 08-10-2026"
    )
