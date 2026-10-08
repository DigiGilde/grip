"""Vacancies end to end in the service layer, against the database."""

from __future__ import annotations

import io
import uuid
from datetime import date
from decimal import Decimal

import pytest
from pypdf import PdfReader
from sqlalchemy import select

from grip.core.config import get_settings
from grip.models.assignment import Assignment, BudgetLine
from grip.models.audit_log import AuditLog
from grip.models.vacancy import (
    DecisionKind,
    StepKind,
    TextKind,
    TextSource,
    VacancyChannel,
    VacancyStatus,
    VacancyType,
)
from grip.services import events
from grip.services.errors import DomainValidationError
from grip.services.llm import LlmNotConfiguredError
from grip.services.vacancies import service
from grip.services.vacancies.drafting import PROMPT_VERSION

REQUESTED = date(2026, 9, 28)
MONDAY = date(2026, 10, 5)


@pytest.fixture
async def budget_line(db_session):
    assignment = Assignment(
        uri=f"https://grip.example/id/opdracht/{uuid.uuid4()}",
        name="Opdracht Alfa",
        kind="external",
    )
    db_session.add(assignment)
    await db_session.flush()
    line = BudgetLine(
        assignment_id=assignment.id,
        description="Backend-ontwikkelaar",
        kind="personnel",
        role="Backend-ontwikkelaar",
        fte=Decimal("0.800"),
        rate_category="C",
        start_date=date(2027, 1, 1),
        end_date=date(2027, 12, 31),
    )
    db_session.add(line)
    await db_session.flush()
    return line


@pytest.fixture
async def requester(create_person):
    return await create_person("aanvrager@example.org", name="Fictieve Aanvrager")


@pytest.fixture
async def vacancy(db_session, budget_line, requester):
    return await service.create_vacancy_from_budget_line(
        db_session,
        actor=requester,
        budget_line_id=budget_line.id,
        contract_type="temporary_project",
        fgr_function_name="Medewerker ICT",
        scale=11,
        addressee_name="Fictief Directielid",
    )


async def _approve(db, vacancy, actor):
    await service.submit_request(db, vacancy.id, actor=actor, requested_on=REQUESTED)
    await service.record_decision(
        db,
        vacancy.id,
        DecisionKind.hr_advice,
        actor=actor,
        person_name="Fictieve Adviseur",
        agreed=True,
        decided_on=date(2026, 9, 29),
    )
    await service.record_decision(
        db,
        vacancy.id,
        DecisionKind.control_advice,
        actor=actor,
        person_name="Fictieve Controller",
        agreed=True,
        note="Past binnen de begroting.",
        decided_on=date(2026, 9, 30),
    )
    await service.record_decision(
        db,
        vacancy.id,
        DecisionKind.approval,
        actor=actor,
        person_name="Fictief Directielid",
        agreed=True,
        decided_on=date(2026, 10, 1),
    )


async def test_a_vacancy_takes_its_values_from_the_budget_line(vacancy, budget_line):
    assert vacancy.function_title == "Backend-ontwikkelaar"
    assert vacancy.fte == Decimal("0.80")
    assert vacancy.start_date == date(2027, 1, 1)
    assert vacancy.end_date == date(2027, 12, 31)
    assert vacancy.declarable is True
    assert vacancy.budget_line_id == budget_line.id
    assert vacancy.status == VacancyStatus.draft.value
    assert vacancy.vacancy_type == VacancyType.regulier.value


async def test_a_vacancy_without_budget_line_is_not_declarable(db_session, requester):
    plain = await service.create_vacancy(
        db_session,
        actor=requester,
        function_title="Teamleider",
        fte=Decimal("1"),
        declarable=False,
    )
    assert plain.budget_line_id is None
    with pytest.raises(DomainValidationError, match="begrotingsregel"):
        await service.create_vacancy(
            db_session,
            actor=requester,
            function_title="Teamleider",
            fte=Decimal("1"),
            declarable=True,
        )


async def test_request_advice_and_approval_become_steps(db_session, vacancy, requester):
    with pytest.raises(DomainValidationError, match="na de aanvraag"):
        await service.record_decision(
            db_session,
            vacancy.id,
            DecisionKind.hr_advice,
            actor=requester,
            person_name="Fictieve Adviseur",
            agreed=True,
        )
    await _approve(db_session, vacancy, requester)

    refreshed = await service._get(db_session, vacancy.id)
    assert refreshed.status == VacancyStatus.approved.value
    assert [step.kind for step in refreshed.steps] == [
        "request",
        "hr_advice",
        "control_advice",
        "approval",
    ]
    assert [step.position for step in refreshed.steps] == [1, 2, 3, 4]
    assert refreshed.requested_on == REQUESTED
    kinds = {d.kind: d for d in refreshed.decisions}
    assert kinds["control_advice"].note == "Past binnen de begroting."
    assert kinds["approval"].recorded_by_id == requester.id


async def test_a_rejected_approval_closes_the_request(db_session, vacancy, requester):
    await service.submit_request(
        db_session, vacancy.id, actor=requester, requested_on=REQUESTED
    )
    for kind in (DecisionKind.hr_advice, DecisionKind.control_advice):
        await service.record_decision(
            db_session,
            vacancy.id,
            kind,
            actor=requester,
            person_name="Fictieve Adviseur",
            agreed=False,
            decided_on=date(2026, 9, 29),
        )
    await service.record_decision(
        db_session,
        vacancy.id,
        DecisionKind.approval,
        actor=requester,
        person_name="Fictief Directielid",
        agreed=False,
        decided_on=date(2026, 10, 1),
    )
    refreshed = await service._get(db_session, vacancy.id)
    assert refreshed.status == VacancyStatus.rejected.value
    with pytest.raises(DomainValidationError, match="akkoord"):
        await service.set_step(
            db_session, vacancy.id, StepKind.internal_opening, started_on=MONDAY
        )


async def test_the_internal_opening_runs_at_least_five_working_days(
    db_session, vacancy, requester
):
    await _approve(db_session, vacancy, requester)
    with pytest.raises(DomainValidationError, match="minimaal 5 werkdagen"):
        await service.set_step(
            db_session,
            vacancy.id,
            StepKind.internal_opening,
            started_on=MONDAY,
            ended_on=date(2026, 10, 8),
        )
    step = await service.set_step(
        db_session,
        vacancy.id,
        StepKind.internal_opening,
        started_on=MONDAY,
        ended_on=date(2026, 10, 9),
    )
    assert step.position == 5
    follow_up = await service.set_step(
        db_session,
        vacancy.id,
        StepKind.priority_candidates,
        started_on=date(2026, 10, 12),
    )
    assert follow_up.position == 6


async def test_a_model_draft_is_stored_with_its_provenance(
    db_session, vacancy, requester, fake_client
):
    draft = await service.draft_text(
        db_session,
        vacancy.id,
        TextKind.vacancy_text,
        actor=requester,
        assignment_summary="Een register bouwen voor fictieve vergunningen.",
        organisation_description="Een team dat digitale producten maakt.",
        client=fake_client,
    )
    assert draft.source == TextSource.model.value
    assert draft.model_id == "testmodel-1"
    assert draft.prompt_version == PROMPT_VERSION
    assert draft.created_at is not None
    assert draft.created_by_id == requester.id
    assert not draft.is_established
    assert draft.body == "Concepttekst van het model."

    assert len(fake_client.calls) == 1
    prompt = fake_client.calls[0]["user"]
    assert "Backend-ontwikkelaar" in prompt
    assert "schaal 11" in prompt
    assert "Opdracht Alfa" in prompt
    # Nothing about people or money reaches the model.
    for forbidden in (
        "Fictieve Aanvrager",
        "Fictief Directielid",
        "aanvrager@example.org",
        "Medewerker ICT",
        "categorie",
        "tarief",
    ):
        assert forbidden not in prompt

    audit = (
        await db_session.execute(
            select(AuditLog).where(AuditLog.entity_id == str(draft.id))
        )
    ).scalar_one()
    assert audit.new_value["model_id"] == "testmodel-1"


async def test_a_person_name_in_the_summary_stops_the_draft(
    db_session, vacancy, requester, fake_client
):
    with pytest.raises(DomainValidationError, match="naam van een persoon"):
        await service.draft_text(
            db_session,
            vacancy.id,
            TextKind.motivation,
            actor=requester,
            assignment_summary="Ter vervanging van Fictieve Aanvrager.",
            client=fake_client,
        )
    assert fake_client.calls == []


async def test_drafting_without_configuration_raises_a_clear_error(
    db_session, vacancy, requester, monkeypatch
):
    settings = get_settings()
    for name in ("VLAM_API_URL", "VLAM_BASE_URL", "VLAM_API_KEY", "VLAM_MODEL_ID"):
        monkeypatch.setattr(settings, name, "")
    with pytest.raises(LlmNotConfiguredError, match="niet geconfigureerd"):
        await service.draft_text(
            db_session, vacancy.id, TextKind.vacancy_text, actor=requester
        )
    # Everything else keeps working without a model.
    text = await service.add_text(
        db_session,
        vacancy.id,
        TextKind.vacancy_text,
        actor=requester,
        body="Zelf geschreven vacaturetekst.",
    )
    assert text.source == TextSource.human.value
    assert text.model_id is None


async def test_a_model_draft_cannot_be_published_until_established(
    db_session, vacancy, requester, fake_client
):
    await _approve(db_session, vacancy, requester)
    draft = await service.draft_text(
        db_session,
        vacancy.id,
        TextKind.vacancy_text,
        actor=requester,
        client=fake_client,
    )
    with pytest.raises(service.TextNotEstablishedError, match="nog niet vastgesteld"):
        await service.publish_vacancy(
            db_session,
            vacancy.id,
            actor=requester,
            channels=[VacancyChannel.internal],
            opened_on=MONDAY,
        )
    refreshed = await service._get(db_session, vacancy.id)
    assert refreshed.status == VacancyStatus.approved.value
    assert refreshed.published_at is None

    await service.establish_text(db_session, draft.id, actor=requester)
    published = await service.publish_vacancy(
        db_session,
        vacancy.id,
        actor=requester,
        channels=[VacancyChannel.internal, VacancyChannel.federated],
        opened_on=MONDAY,
    )
    assert published.status == VacancyStatus.open.value
    assert published.channels == ["federated", "internal"]
    assert published.published_at is not None
    assert any(step.kind == "internal_opening" for step in published.steps)


async def test_a_rewritten_draft_still_shows_the_model_was_involved(
    db_session, vacancy, requester, fake_client
):
    draft = await service.draft_text(
        db_session, vacancy.id, TextKind.motivation, actor=requester, client=fake_client
    )
    rewritten = await service.add_text(
        db_session,
        vacancy.id,
        TextKind.motivation,
        actor=requester,
        body="Door een mens herschreven motivatie.",
        based_on_id=draft.id,
    )
    await service.establish_text(db_session, rewritten.id, actor=requester)

    released = await service.text_for_release(
        db_session, vacancy.id, TextKind.motivation
    )
    assert released.id == rewritten.id
    assert released.source == TextSource.human.value
    origin = await service.model_assisted(db_session, released)
    assert origin is not None and origin.id == draft.id
    assert origin.model_id == "testmodel-1"

    own = await service.add_text(
        db_session,
        vacancy.id,
        TextKind.vacancy_text,
        actor=requester,
        body="Helemaal zelf geschreven.",
    )
    assert await service.model_assisted(db_session, own) is None


async def test_publishing_needs_approval_and_is_not_for_a_ready_candidate(
    db_session, vacancy, requester, budget_line
):
    text = await service.add_text(
        db_session,
        vacancy.id,
        TextKind.vacancy_text,
        actor=requester,
        body="Vacaturetekst.",
    )
    await service.establish_text(db_session, text.id, actor=requester)
    with pytest.raises(DomainValidationError, match="akkoord"):
        await service.publish_vacancy(
            db_session, vacancy.id, actor=requester, channels=["internal"]
        )

    ready = await service.create_vacancy_from_budget_line(
        db_session,
        actor=requester,
        budget_line_id=budget_line.id,
        vacancy_type=VacancyType.gerede,
    )
    with pytest.raises(DomainValidationError, match="aparte procedure"):
        await service.publish_vacancy(
            db_session, ready.id, actor=requester, channels=["internal"]
        )


async def test_publishing_emits_an_event_once_the_type_is_registered(
    db_session, vacancy, requester, monkeypatch
):
    await _approve(db_session, vacancy, requester)
    text = await service.add_text(
        db_session,
        vacancy.id,
        TextKind.vacancy_text,
        actor=requester,
        body="Vacaturetekst.",
    )
    await service.establish_text(db_session, text.id, actor=requester)

    received: list[dict] = []

    async def handler(_session, _event_type, payload):
        received.append(payload)

    monkeypatch.setattr(
        events, "EVENT_TYPES", (*events.EVENT_TYPES, service.VACANCY_PUBLISHED)
    )
    events.register_handler(service.VACANCY_PUBLISHED, handler)
    try:
        await service.publish_vacancy(
            db_session,
            vacancy.id,
            actor=requester,
            channels=["federated"],
            opened_on=MONDAY,
        )
    finally:
        events.unregister_handler(service.VACANCY_PUBLISHED, handler)
    assert received == [
        {
            "vacancy_id": str(vacancy.id),
            "text_id": str(text.id),
            "channels": ["federated"],
        }
    ]


async def test_the_request_form_is_filled_from_the_vacancy(
    db_session, vacancy, requester, blank_form, test_mapping, fake_client
):
    with pytest.raises(service.NoFormTemplateError):
        await service.build_request_form(db_session, vacancy.id)

    template = await service.upload_form_template(
        db_session,
        actor=requester,
        name="Testformulier",
        file_name="testformulier.pdf",
        content=blank_form,
        mapping=test_mapping,
    )
    assert template.is_active

    await service.submit_request(
        db_session, vacancy.id, actor=requester, requested_on=REQUESTED
    )
    # HR decided; the controller is known but has not decided yet.
    await service.record_decision(
        db_session,
        vacancy.id,
        DecisionKind.hr_advice,
        actor=requester,
        person_name="Fictieve Adviseur",
        agreed=True,
        note="Akkoord.",
        decided_on=date(2026, 9, 29),
    )
    await service.record_decision(
        db_session,
        vacancy.id,
        DecisionKind.control_advice,
        actor=requester,
        person_name="Fictieve Controller",
    )
    # A model draft of the motivation that nobody established.
    await service.draft_text(
        db_session, vacancy.id, TextKind.motivation, actor=requester, client=fake_client
    )

    generated = await service.build_request_form(db_session, vacancy.id)
    assert generated.file_name == "aanvraagformulier-vacature-backend-ontwikkelaar.pdf"
    reader = PdfReader(io.BytesIO(generated.content))
    fields = reader.get_fields()
    assert fields["aanvrager"]["/V"] == "Fictieve Aanvrager"
    assert fields["datum"]["/V"] == "28-9-2026"
    assert fields["aan"]["/V"] == "Fictief Directielid"
    assert fields["functie"]["/V"] == "Backend-ontwikkelaar"
    assert fields["fgr"]["/V"] == "Medewerker ICT"
    assert fields["schaal"]["/V"] == "11"
    assert fields["fte"]["/V"] == "0,8"
    assert fields["decl_ja"]["/V"] == "/Ja"
    assert fields["type_regulier"]["/V"] == "/Ja"
    assert fields["contract_project"]["/V"] == "/Ja"
    assert fields["hr_naam"]["/V"] == "Fictieve Adviseur"
    assert fields["hr_wel"]["/V"] == "/Ja"
    assert fields["hr_toelichting"]["/V"] == "Akkoord."
    assert fields["controller"]["/V"] == "Fictieve Controller"
    # Open for completion outside grip.
    assert fields["control_wel"]["/V"] == "/Off"
    assert not fields["akkoord_naam"].get("/V")
    assert fields["akkoord_wel"]["/V"] == "/Off"
    # The draft did not leave grip.
    assert not fields["motivatie"].get("/V")
    assert "motivation" in generated.open_sources
    assert "approval_decision" in generated.open_sources

    text = await service.add_text(
        db_session,
        vacancy.id,
        TextKind.motivation,
        actor=requester,
        body="De rol is nodig om het register op tijd te leveren.",
    )
    await service.establish_text(db_session, text.id, actor=requester)
    again = await service.build_request_form(db_session, vacancy.id)
    fields = PdfReader(io.BytesIO(again.content)).get_fields()
    assert fields["motivatie"]["/V"] == (
        "De rol is nodig om het register op tijd te leveren."
    )
    assert "motivation" not in again.open_sources


async def test_a_filled_form_is_refused_as_template_unless_cleared(
    db_session, requester, filled_form, blank_form, test_mapping
):
    with pytest.raises(DomainValidationError, match="al ingevuld"):
        await service.upload_form_template(
            db_session,
            actor=requester,
            name="Ingevuld",
            file_name="ingevuld.pdf",
            content=filled_form,
            mapping=test_mapping,
        )
    first = await service.upload_form_template(
        db_session,
        actor=requester,
        name="Leeggemaakt",
        file_name="leeg.pdf",
        content=filled_form,
        mapping=test_mapping,
        clear_values=True,
    )
    assert b"Fictieve Aanvrager" not in first.content

    second = await service.upload_form_template(
        db_session,
        actor=requester,
        name="Nieuw",
        file_name="nieuw.pdf",
        content=blank_form,
        mapping=test_mapping,
    )
    await db_session.refresh(first)
    assert second.is_active and not first.is_active

    with pytest.raises(DomainValidationError, match="onbekend gegeven"):
        await service.upload_form_template(
            db_session,
            actor=requester,
            name="Fout",
            file_name="fout.pdf",
            content=blank_form,
            mapping={
                "fields": [{"name": "aanvrager", "type": "text", "source": "kpi"}]
            },
        )
