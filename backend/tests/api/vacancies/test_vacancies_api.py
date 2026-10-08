"""The vacancy routes: what each kind of viewer may do and see."""

from __future__ import annotations

import io
import json

from pypdf import PdfReader

BASE = "/api/vacancies"
NAME_FIELDS = {"requester_id", "requester_name", "addressee_name"}


async def _create(client, budget_line, **extra):
    body = {
        "budget_line_id": str(budget_line.id),
        "contract_type": "temporary_project",
        "fgr_function_name": "Medewerker ICT",
        "scale": 11,
        "addressee_name": "Fictief Directielid",
        **extra,
    }
    response = await client.post(BASE, json=body)
    assert response.status_code == 201, response.text
    return response.json()


async def _motivate(client, vacancy_id):
    """Write and settle the motivation: a request cannot be made without it."""
    response = await client.post(
        f"{BASE}/{vacancy_id}/texts",
        json={"kind": "motivation", "body": "De rol is nog niet ingevuld."},
    )
    assert response.status_code == 201, response.text
    response = await client.post(
        f"{BASE}/{vacancy_id}/texts/{response.json()['texts'][-1]['id']}/establish"
    )
    assert response.status_code == 200, response.text


async def _decide(client, vacancy_id, kind, **body):
    return await client.put(f"{BASE}/{vacancy_id}/decisions/{kind}", json=body)


async def _approve(client, act_as, beheerder, vacancy_id):
    """Submit and get both advices and the approval, as the beheerder."""
    act_as(beheerder)
    await _motivate(client, vacancy_id)
    response = await client.post(
        f"{BASE}/{vacancy_id}/submit", json={"requested_on": "2026-09-28"}
    )
    assert response.status_code == 200, response.text
    for kind, day in (
        ("hr_advice", "2026-09-29"),
        ("control_advice", "2026-09-30"),
        ("approval", "2026-10-01"),
    ):
        response = await _decide(
            client,
            vacancy_id,
            kind,
            person_name=f"Fictieve {kind}",
            agreed=True,
            decided_on=day,
        )
        assert response.status_code == 200, response.text
    return response.json()


async def _publish(client, act_as, beheerder, vacancy_id):
    await _approve(client, act_as, beheerder, vacancy_id)
    response = await client.post(
        f"{BASE}/{vacancy_id}/texts",
        json={"kind": "vacancy_text", "body": "Wij zoeken een ontwikkelaar."},
    )
    assert response.status_code == 201, response.text
    text_id = response.json()["texts"][-1]["id"]
    response = await client.post(f"{BASE}/{vacancy_id}/texts/{text_id}/establish")
    assert response.status_code == 200, response.text
    response = await client.post(
        f"{BASE}/{vacancy_id}/publish",
        json={"channels": ["internal"], "opened_on": "2026-10-05"},
    )
    assert response.status_code == 200, response.text
    return response.json()


# --- creating ----------------------------------------------------------------


async def test_manager_creates_on_own_budget_line(
    client, act_as, manager, budget_line
) -> None:
    act_as(manager)
    vacancy = await _create(client, budget_line)
    assert vacancy["function_title"] == "Backend-ontwikkelaar"
    assert float(vacancy["fte"]) == 0.8
    assert vacancy["declarable"] is True
    assert vacancy["status"] == "draft"
    assert vacancy["assignment_name"] == "Opdracht Alfa"
    assert vacancy["requester_name"] == "Fictieve Eigenaar"
    assert vacancy["permissions"]["can_edit"] is True
    # Decisions can only be recorded after the request.
    assert vacancy["permissions"]["can_record_approval"] is False
    steps = {step["kind"]: step for step in vacancy["procedure"]}
    assert steps["internal_opening"]["minimum_working_days"] == 5
    assert steps["request"]["recorded"] is False


async def test_manager_cannot_create_on_another_assignment(
    client, act_as, manager, other_budget_line
) -> None:
    act_as(manager)
    response = await client.post(
        BASE, json={"budget_line_id": str(other_budget_line.id)}
    )
    assert response.status_code == 403
    assert response.headers["content-type"].startswith("application/problem+json")


async def test_without_budget_line_is_for_planner_and_beheerder(
    client, act_as, manager, planner
) -> None:
    body = {"function_title": "Teamleider", "fte": "1", "scale": 13}
    act_as(manager)
    assert (await client.post(BASE, json=body)).status_code == 403
    act_as(planner)
    response = await client.post(BASE, json=body)
    assert response.status_code == 201, response.text
    vacancy = response.json()
    assert vacancy["declarable"] is False
    assert vacancy["budget_line_id"] is None
    # Function and fte are needed without a budget line.
    response = await client.post(BASE, json={"scale": 13})
    assert response.status_code == 422


async def test_colleague_cannot_create(client, act_as, colleague, budget_line) -> None:
    act_as(colleague)
    response = await client.post(BASE, json={"budget_line_id": str(budget_line.id)})
    assert response.status_code == 403


async def test_unfilled_roles_follow_the_assignments_you_manage(
    client, act_as, manager, planner, colleague, budget_line, other_budget_line
) -> None:
    act_as(manager)
    roles = (await client.get(f"{BASE}/unfilled-roles")).json()
    assert [role["budget_line_id"] for role in roles] == [str(budget_line.id)]
    assert float(roles[0]["unfilled_fte"]) == 0.8
    assert roles[0]["declarable"] is True

    act_as(planner)
    roles = (await client.get(f"{BASE}/unfilled-roles")).json()
    assert {role["assignment_name"] for role in roles} == {
        "Opdracht Alfa",
        "Opdracht Beta",
    }

    act_as(colleague)
    assert (await client.get(f"{BASE}/unfilled-roles")).json() == []

    # A line with a running vacancy is no longer offered.
    act_as(manager)
    await _create(client, budget_line)
    assert (await client.get(f"{BASE}/unfilled-roles")).json() == []


async def test_update_only_what_is_sent(client, act_as, manager, budget_line) -> None:
    act_as(manager)
    vacancy = await _create(client, budget_line)
    response = await client.patch(
        f"{BASE}/{vacancy['id']}", json={"scale": 12, "addressee_name": None}
    )
    assert response.status_code == 200, response.text
    changed = response.json()
    assert changed["scale"] == 12
    assert changed["addressee_name"] is None
    assert changed["fgr_function_name"] == "Medewerker ICT"


# --- who sees what -----------------------------------------------------------


async def test_draft_is_invisible_without_a_role(
    client, act_as, manager, colleague, budget_line
) -> None:
    act_as(manager)
    vacancy = await _create(client, budget_line)
    act_as(colleague)
    response = await client.get(f"{BASE}/{vacancy['id']}")
    assert response.status_code == 404
    unknown = await client.get(f"{BASE}/00000000-0000-0000-0000-000000000000")
    assert unknown.status_code == 404
    # Not telling apart "exists but hidden" from "does not exist".
    assert response.json() == unknown.json()
    assert (await client.get(BASE)).json() == []
    assert (await client.get(f"{BASE}/open-roles")).json() == []
    for method, path, body in (
        ("patch", "", {"scale": 12}),
        ("post", "/submit", {}),
        ("post", "/texts", {"kind": "vacancy_text", "body": "x"}),
        ("post", "/texts/draft", {"kind": "vacancy_text"}),
        ("post", "/publish", {"channels": ["internal"]}),
        ("put", "/steps/internal_opening", {"started_on": "2026-10-05"}),
        ("put", "/decisions/approval", {"person_name": "x", "agreed": True}),
    ):
        response = await getattr(client, method)(
            f"{BASE}/{vacancy['id']}{path}", json=body
        )
        assert response.status_code == 404, (method, path)
    assert (await client.get(f"{BASE}/{vacancy['id']}/request-form")).status_code == 404


async def test_lezer_sees_the_vacancy_without_names(
    client, act_as, manager, beheerder, lezer, budget_line
) -> None:
    act_as(manager)
    vacancy = await _create(client, budget_line)
    await _approve(client, act_as, beheerder, vacancy["id"])

    act_as(lezer)
    response = await client.get(f"{BASE}/{vacancy['id']}")
    assert response.status_code == 200
    seen = response.json()
    assert not NAME_FIELDS & seen.keys()
    assert seen["status"] == "approved"
    assert seen["assignment_name"] == "Opdracht Alfa"
    assert len(seen["decisions"]) == 3
    for decision in seen["decisions"]:
        assert decision["agreed"] is True
        assert not {"person_name", "note", "has_account"} & decision.keys()
    for step in seen["procedure"]:
        assert "note" not in step
    assert seen["permissions"] == {
        "can_edit": False,
        "can_record_hr_advice": False,
        "can_record_control_advice": False,
        "can_record_approval": False,
        "can_download_form": False,
        "can_withdraw": False,
        "can_fill": False,
    }
    assert "Fictie" not in json.dumps({k: v for k, v in seen.items() if k != "id"})

    listed = (await client.get(BASE)).json()
    assert len(listed) == 1
    assert "requester_name" not in listed[0]
    assert listed[0]["current_step"] == "Akkoord"
    assert listed[0]["next_step"] == "Interne openstelling"

    # Reading is all a lezer does.
    assert (
        await client.patch(f"{BASE}/{vacancy['id']}", json={"scale": 12})
    ).status_code == 403
    assert (await client.get(f"{BASE}/{vacancy['id']}/request-form")).status_code == 403
    assert (
        await client.get(f"{BASE}/{vacancy['id']}/request-form/status")
    ).status_code == 403


async def test_published_vacancy_is_public_without_names(
    client, act_as, manager, beheerder, colleague, budget_line
) -> None:
    act_as(manager)
    vacancy = await _create(client, budget_line)
    await _publish(client, act_as, beheerder, vacancy["id"])

    act_as(colleague)
    response = await client.get(f"{BASE}/{vacancy['id']}")
    assert response.status_code == 200
    seen = response.json()
    assert set(seen) == {
        "id",
        "function_title",
        "fgr_function_name",
        "scale",
        "fte",
        "start_date",
        "end_date",
        "status",
        "published_at",
        "published_text",
        "permissions",
    }
    assert seen["published_text"]["body"] == "Wij zoeken een ontwikkelaar."
    assert seen["published_text"]["model_assisted"] is False
    assert not any(seen["permissions"].values())
    assert "Fictie" not in response.text and "Opdracht Alfa" not in response.text

    roles = (await client.get(f"{BASE}/open-roles")).json()
    assert len(roles) == 1
    assert roles[0]["function_title"] == "Backend-ontwikkelaar"
    assert roles[0]["text"]["body"] == "Wij zoeken een ontwikkelaar."
    listed = (await client.get(BASE)).json()
    assert set(listed[0]) == {
        "id",
        "function_title",
        "scale",
        "fte",
        "start_date",
        "end_date",
        "status",
    }
    # Still read-only.
    assert (
        await client.patch(f"{BASE}/{vacancy['id']}", json={"scale": 12})
    ).status_code == 403


async def test_options_for_everyone(client, act_as, colleague, beheerder) -> None:
    act_as(colleague)
    options = (await client.get(f"{BASE}/options")).json()
    assert {o["value"] for o in options["vacancy_types"]} == {
        "regulier",
        "specialistisch",
        "beoogd",
        "gerede",
    }
    assert options["drafting_available"] is False
    assert options["request_form_available"] is False
    assert options["can_create_without_budget_line"] is False
    assert options["can_manage_setup"] is False
    opening = next(s for s in options["steps"] if s["value"] == "internal_opening")
    assert opening["minimum_working_days"] == 5

    act_as(beheerder)
    options = (await client.get(f"{BASE}/options")).json()
    assert options["can_create_without_budget_line"] is True
    assert options["can_manage_setup"] is True


# --- advice and approval -----------------------------------------------------


async def test_naming_is_editing_and_deciding_is_not(
    client, act_as, manager, planner, adviser, beheerder, budget_line
) -> None:
    act_as(manager)
    vacancy = await _create(client, budget_line)
    vid = vacancy["id"]
    # Before the request nothing can be recorded.
    response = await _decide(client, vid, "hr_advice", person_name="Fictieve Adviseur")
    assert response.status_code == 422
    await _motivate(client, vid)
    await client.post(f"{BASE}/{vid}/submit", json={"requested_on": "2026-09-28"})

    # The manager names the adviser, with the account.
    response = await _decide(
        client,
        vid,
        "hr_advice",
        person_name="Fictieve Adviseur",
        person_email="ADVISEUR@example.org",
    )
    assert response.status_code == 200, response.text
    decision = response.json()["decisions"][0]
    assert decision["agreed"] is None and decision["has_account"] is True

    # An address without an account is refused.
    response = await _decide(
        client,
        vid,
        "control_advice",
        person_name="X",
        person_email="niemand@example.org",
    )
    assert response.status_code == 422

    # Neither the manager nor a planner records the decision itself.
    for person in (manager, planner):
        act_as(person)
        response = await _decide(
            client, vid, "hr_advice", person_name="Fictieve Adviseur", agreed=True
        )
        assert response.status_code == 403

    # The named adviser sees the request and records the advice; the name stays.
    act_as(adviser)
    seen = (await client.get(f"{BASE}/{vid}")).json()
    assert seen["requester_name"] == "Fictieve Eigenaar"
    assert seen["permissions"]["can_record_hr_advice"] is True
    assert seen["permissions"]["can_record_approval"] is False
    assert seen["permissions"]["can_edit"] is False
    response = await _decide(
        client,
        vid,
        "hr_advice",
        person_name="Iemand Anders",
        agreed=True,
        note="Akkoord, past in de formatie.",
        decided_on="2026-09-29",
    )
    assert response.status_code == 200, response.text
    decision = response.json()["decisions"][0]
    assert decision["person_name"] == "Fictieve Adviseur"
    assert decision["agreed"] is True and decision["decided_on"] == "2026-09-29"
    # Not named for the approval.
    response = await _decide(client, vid, "approval", person_name="X", agreed=True)
    assert response.status_code == 403

    # Once decided, changing the name is changing the decision.
    act_as(manager)
    response = await _decide(client, vid, "hr_advice", person_name="Iemand Anders")
    assert response.status_code == 403

    act_as(beheerder)
    response = await _decide(
        client, vid, "control_advice", person_name="Fictieve Controller", agreed=True
    )
    assert response.status_code == 200
    response = await _decide(
        client, vid, "approval", person_name="Fictief Directielid", agreed=False
    )
    assert response.status_code == 200
    assert response.json()["status"] == "rejected"


# --- the procedure -----------------------------------------------------------


async def test_opening_steps_and_the_minimum(
    client, act_as, manager, beheerder, budget_line
) -> None:
    act_as(manager)
    vacancy = await _create(client, budget_line)
    vid = vacancy["id"]
    await _publish(client, act_as, beheerder, vid)

    act_as(manager)
    # Monday 5 October 2026: five working days end on Friday the 9th.
    response = await client.put(
        f"{BASE}/{vid}/steps/internal_opening",
        json={"started_on": "2026-10-05", "ended_on": "2026-10-08"},
    )
    assert response.status_code == 422
    assert "minimaal 5 werkdagen" in response.json()["detail"]
    response = await client.put(
        f"{BASE}/{vid}/steps/internal_opening",
        json={"started_on": "2026-10-05", "ended_on": "2026-10-09"},
    )
    assert response.status_code == 200, response.text
    step = next(
        s for s in response.json()["procedure"] if s["kind"] == "internal_opening"
    )
    assert step["earliest_end"] == "2026-10-09" and step["recorded"] is True

    # The request and the decisions get their dates elsewhere.
    response = await client.put(
        f"{BASE}/{vid}/steps/approval", json={"started_on": "2026-10-01"}
    )
    assert response.status_code == 422
    # Out of order.
    response = await client.put(
        f"{BASE}/{vid}/steps/external_market", json={"started_on": "2026-10-12"}
    )
    assert response.status_code == 422


async def test_ready_candidate_is_not_opened(
    client, act_as, manager, beheerder, colleague, budget_line
) -> None:
    act_as(manager)
    vacancy = await _create(
        client,
        budget_line,
        vacancy_type="gerede",
        candidate_person_id=str(colleague.id),
    )
    assert vacancy["has_openings"] is False
    assert [s["kind"] for s in vacancy["procedure"]] == [
        "request",
        "hr_advice",
        "control_advice",
        "approval",
    ]
    await _approve(client, act_as, beheerder, vacancy["id"])
    response = await client.post(
        f"{BASE}/{vacancy['id']}/publish", json={"channels": ["internal"]}
    )
    assert response.status_code == 422


# --- texts -------------------------------------------------------------------


async def test_drafting_without_a_model_is_a_clear_503(
    client, act_as, manager, budget_line
) -> None:
    act_as(manager)
    vacancy = await _create(client, budget_line)
    response = await client.post(
        f"{BASE}/{vacancy['id']}/texts/draft", json={"kind": "vacancy_text"}
    )
    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/problem+json")
    problem = response.json()
    assert problem["title"] == "Taalmodel niet ingesteld"
    assert problem["code"] == "LlmNotConfiguredError"
    assert "niet geconfigureerd" in problem["detail"]
    # Everything else still works.
    response = await client.post(
        f"{BASE}/{vacancy['id']}/texts",
        json={"kind": "motivation", "body": "De rol is nog niet ingevuld."},
    )
    assert response.status_code == 201


async def test_model_draft_keeps_its_origin_and_needs_a_person(
    client, act_as, manager, beheerder, colleague, budget_line, fake_model
) -> None:
    act_as(manager)
    vacancy = await _create(client, budget_line)
    vid = vacancy["id"]
    response = await client.post(
        f"{BASE}/{vid}/texts/draft",
        json={
            "kind": "vacancy_text",
            "assignment_summary": "Een dienst voor het aanvragen van vergunningen.",
        },
    )
    assert response.status_code == 201, response.text
    draft = response.json()["texts"][-1]
    assert draft["source"] == "model" and draft["model_id"] == "testmodel-1"
    assert draft["model_assisted"] is True and draft["established_at"] is None
    assert draft["created_by_name"] == "Fictieve Eigenaar"

    sent = fake_model.calls[0]["user"]
    assert "vergunningen" in sent
    # No name of a person of the instance goes to the model.
    for name in ("Fictieve Eigenaar", "Fictief Directielid", "Fictieve Beheerder"):
        assert name not in sent and name not in fake_model.calls[0]["system"]

    # A summary that names a colleague is refused.
    response = await client.post(
        f"{BASE}/{vid}/texts/draft",
        json={"kind": "vacancy_text", "assignment_summary": "Met Fictieve Collega."},
    )
    assert response.status_code == 422
    assert len(fake_model.calls) == 1

    # The draft alone does not let the vacancy out.
    await _approve(client, act_as, beheerder, vid)
    response = await client.post(
        f"{BASE}/{vid}/publish", json={"channels": ["internal"]}
    )
    assert response.status_code == 422
    assert "nog niet vastgesteld" in response.json()["detail"]

    # A person rewrites the draft and establishes the new version.
    response = await client.post(
        f"{BASE}/{vid}/texts",
        json={
            "kind": "vacancy_text",
            "body": "Herschreven tekst.",
            "based_on_id": draft["id"],
        },
    )
    rewritten = response.json()["texts"][-1]
    assert rewritten["source"] == "human" and rewritten["model_assisted"] is True
    assert rewritten["origin_model_id"] == "testmodel-1"
    response = await client.post(f"{BASE}/{vid}/texts/{rewritten['id']}/establish")
    assert response.status_code == 200
    current = [
        t
        for t in response.json()["texts"]
        if t["is_current"] and t["kind"] == "vacancy_text"
    ]
    assert [t["id"] for t in current] == [rewritten["id"]]
    assert current[0]["established_by_name"] == "Fictieve Beheerder"

    response = await client.post(
        f"{BASE}/{vid}/publish", json={"channels": ["internal", "federated"]}
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "open"

    # Everyone sees that a model was involved, with which model and when.
    act_as(colleague)
    public = (await client.get(f"{BASE}/{vid}")).json()["published_text"]
    assert public["body"] == "Herschreven tekst."
    assert public["model_assisted"] is True and public["model_id"] == "testmodel-1"
    assert public["drafted_at"] is not None


async def test_establishing_a_text_of_another_vacancy(
    client, act_as, beheerder, budget_line, other_budget_line
) -> None:
    act_as(beheerder)
    first = await _create(client, budget_line)
    second = await _create(client, other_budget_line)
    response = await client.post(
        f"{BASE}/{first['id']}/texts", json={"kind": "motivation", "body": "Tekst."}
    )
    text_id = response.json()["texts"][-1]["id"]
    response = await client.post(f"{BASE}/{second['id']}/texts/{text_id}/establish")
    assert response.status_code == 404


# --- the request form and its template ---------------------------------------


async def _upload(client, content, mapping, **fields):
    return await client.post(
        "/api/form-templates",
        data={"name": "Aanvraagformulier", "mapping": json.dumps(mapping), **fields},
        files={"file": ("formulier.pdf", content, "application/pdf")},
    )


async def test_setup_is_for_the_beheerder_only(
    client, act_as, planner, lezer, manager, colleague, blank_form, test_mapping
) -> None:
    for person in (planner, lezer, manager, colleague):
        act_as(person)
        assert (await client.get("/api/form-templates")).status_code == 403
        response = await client.get("/api/form-templates/bundled-mappings")
        assert response.status_code == 403
        assert (await _upload(client, blank_form, test_mapping)).status_code == 403
        response = await client.post(
            "/api/form-templates/inspect",
            files={"file": ("formulier.pdf", blank_form, "application/pdf")},
        )
        assert response.status_code == 403
        response = await client.post(
            "/api/form-templates/00000000-0000-0000-0000-000000000000/activate"
        )
        assert response.status_code == 403
        assert (await client.get(f"{BASE}/language-model")).status_code == 403


async def test_template_upload_inspection_and_activation(
    client, act_as, beheerder, blank_form, filled_form, test_mapping
) -> None:
    act_as(beheerder)
    bundled = (await client.get("/api/form-templates/bundled-mappings")).json()
    assert bundled and bundled[0]["mapping"]["fields"]

    # Inspection shows the fields and that the form is filled in, never values.
    response = await client.post(
        "/api/form-templates/inspect",
        data={"mapping": json.dumps(test_mapping)},
        files={"file": ("formulier.pdf", filled_form, "application/pdf")},
    )
    assert response.status_code == 200, response.text
    inspection = response.json()
    assert inspection["has_values"] is True
    assert "al ingevuld" in inspection["problem"]
    by_name = {field["name"]: field for field in inspection["fields"]}
    assert by_name["aanvrager"] == {
        "name": "aanvrager",
        "type": "text",
        "states": [],
        "has_value": True,
        "source": "requester_name",
        "label": None,
    }
    assert "Fictieve Aanvrager" not in response.text

    # A filled form is refused as template, unless it is cleared first.
    response = await _upload(client, filled_form, test_mapping)
    assert response.status_code == 422
    assert "al ingevuld" in response.json()["detail"]
    response = await _upload(client, filled_form, test_mapping, clear_values="true")
    assert response.status_code == 201, response.text
    first = response.json()
    assert (
        first["is_active"] is True and first["uploaded_by_name"] == "Fictieve Beheerder"
    )

    response = await _upload(client, blank_form, test_mapping)
    second = response.json()
    listed = (await client.get("/api/form-templates")).json()
    assert {t["id"]: t["is_active"] for t in listed} == {
        first["id"]: False,
        second["id"]: True,
    }
    response = await client.post(f"/api/form-templates/{first['id']}/activate")
    assert response.status_code == 200 and response.json()["is_active"] is True
    listed = (await client.get("/api/form-templates")).json()
    assert {t["id"]: t["is_active"] for t in listed} == {
        first["id"]: True,
        second["id"]: False,
    }

    # Not a pdf, and a mapping that is not JSON.
    response = await _upload(client, b"geen pdf", test_mapping)
    assert response.status_code == 422
    response = await client.post(
        "/api/form-templates",
        data={"name": "x", "mapping": "{geen json"},
        files={"file": ("formulier.pdf", blank_form, "application/pdf")},
    )
    assert response.status_code == 422


async def test_request_form_download(
    client, act_as, manager, beheerder, adviser, budget_line, blank_form, test_mapping
) -> None:
    act_as(manager)
    vacancy = await _create(client, budget_line)
    vid = vacancy["id"]

    # Without a template there is nothing to download.
    status = (await client.get(f"{BASE}/{vid}/request-form/status")).json()
    assert status == {
        "available": False,
        "file_name": None,
        "open_fields": [],
        "motivation_established": False,
    }
    assert (await client.get(f"{BASE}/{vid}/request-form")).status_code == 422

    act_as(beheerder)
    assert (await _upload(client, blank_form, test_mapping)).status_code == 201

    act_as(manager)
    await _motivate(client, vid)
    await client.post(f"{BASE}/{vid}/submit", json={"requested_on": "2026-09-28"})
    await _decide(
        client,
        vid,
        "hr_advice",
        person_name="Fictieve Adviseur",
        person_email="adviseur@example.org",
    )
    status = (await client.get(f"{BASE}/{vid}/request-form/status")).json()
    assert status["available"] is True
    assert status["file_name"] == "aanvraagformulier-vacature-backend-ontwikkelaar.pdf"
    open_sources = {field["source"] for field in status["open_fields"]}
    # The motivation was settled before the request, so the form has it.
    assert "motivation" not in open_sources and "approver_name" in open_sources
    assert "requester_name" not in open_sources

    response = await client.get(f"{BASE}/{vid}/request-form")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert "attachment" in response.headers["content-disposition"]
    assert response.headers["cache-control"] == "no-store"
    fields = PdfReader(io.BytesIO(response.content)).get_fields()
    assert fields["aanvrager"]["/V"] == "Fictieve Eigenaar"
    assert fields["functie"]["/V"] == "Backend-ontwikkelaar"
    assert fields["datum"]["/V"] == "28-9-2026"
    assert fields["hr_naam"]["/V"] == "Fictieve Adviseur"
    assert fields["decl_ja"]["/V"] == "/Ja"
    # Settled before the request, so it is on the form.
    assert fields["motivatie"]["/V"] == "De rol is nog niet ingevuld."

    # The named adviser gets the form too.
    act_as(adviser)
    assert (await client.get(f"{BASE}/{vid}/request-form")).status_code == 200


async def test_language_model_configuration(client, act_as, beheerder) -> None:
    act_as(beheerder)
    model = (await client.get(f"{BASE}/language-model")).json()
    assert model["configured"] is False
    assert "VLAM_MODEL_ID" in model["missing_settings"]
    assert model["available_models"] is None
    checked = (await client.get(f"{BASE}/language-model?check=true")).json()
    assert "nog niet volledig ingesteld" in checked["check_error"]


# --- withdrawing and filling --------------------------------------------------


async def test_withdraw_takes_a_vacancy_off_the_open_roles(
    client, act_as, manager, beheerder, colleague, budget_line
) -> None:
    act_as(manager)
    vacancy = await _create(client, budget_line)
    opened = await _publish(client, act_as, beheerder, vacancy["id"])
    assert opened["permissions"]["can_withdraw"] is True
    assert opened["permissions"]["can_fill"] is True

    act_as(colleague)
    assert (
        await client.post(f"{BASE}/{vacancy['id']}/withdraw", json={})
    ).status_code in (403, 404)

    act_as(manager)
    response = await client.post(
        f"{BASE}/{vacancy['id']}/withdraw", json={"note": "Opdracht vervalt."}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "withdrawn"
    assert body["permissions"]["can_withdraw"] is False
    assert body["permissions"]["can_fill"] is False

    act_as(colleague)
    assert (await client.get(f"{BASE}/open-roles")).json() == []
    assert (await client.get(f"{BASE}/{vacancy['id']}")).status_code == 404

    # Final: not twice, and not filled afterwards.
    act_as(manager)
    for action in ("withdraw", "fill"):
        refused = await client.post(f"{BASE}/{vacancy['id']}/{action}", json={})
        assert refused.status_code == 422, action


async def test_fill_needs_the_approval(
    client, act_as, manager, beheerder, budget_line
) -> None:
    act_as(manager)
    vacancy = await _create(client, budget_line)
    assert vacancy["permissions"]["can_fill"] is False
    assert vacancy["permissions"]["can_withdraw"] is True
    refused = await client.post(f"{BASE}/{vacancy['id']}/fill", json={})
    assert refused.status_code == 422
    assert "akkoord" in refused.json()["detail"]

    approved = await _approve(client, act_as, beheerder, vacancy["id"])
    assert approved["permissions"]["can_fill"] is True
    act_as(manager)
    response = await client.post(f"{BASE}/{vacancy['id']}/fill", json={})
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "filled"


async def test_a_ready_candidate_is_filled_without_opening(
    client, act_as, manager, beheerder, colleague, budget_line
) -> None:
    act_as(manager)
    vacancy = await _create(
        client,
        budget_line,
        vacancy_type="gerede",
        candidate_person_id=str(colleague.id),
    )
    await _approve(client, act_as, beheerder, vacancy["id"])
    response = await client.post(f"{BASE}/{vacancy['id']}/fill", json={})
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "filled"


async def test_naming_a_person_of_the_instance_by_id(
    client, act_as, manager, beheerder, colleague, budget_line
) -> None:
    act_as(manager)
    vacancy = await _create(client, budget_line)
    await _motivate(client, vacancy["id"])
    await client.post(f"{BASE}/{vacancy['id']}/submit", json={})

    # Picked from the list: the name comes from the person record.
    response = await _decide(
        client, vacancy["id"], "hr_advice", person_id=str(colleague.id)
    )
    assert response.status_code == 200, response.text
    named = next(d for d in response.json()["decisions"] if d["kind"] == "hr_advice")
    assert named["person_name"] == colleague.name
    assert named["has_account"] is True

    # Someone without an account is named in free text.
    response = await _decide(
        client, vacancy["id"], "control_advice", person_name="Fictieve Controller"
    )
    assert response.status_code == 200, response.text
    named = next(
        d for d in response.json()["decisions"] if d["kind"] == "control_advice"
    )
    assert named["person_name"] == "Fictieve Controller"
    assert named["has_account"] is False

    # Nobody named at all, or an unknown person, is refused.
    assert (await _decide(client, vacancy["id"], "approval")).status_code == 422
    from uuid import uuid4

    refused = await _decide(client, vacancy["id"], "approval", person_id=str(uuid4()))
    assert refused.status_code == 422
    assert "account" in refused.json()["detail"]


async def test_list_says_which_step_and_what_it_waits_on(
    client, act_as, manager, beheerder, colleague, budget_line
) -> None:
    """The step is named as on the vacancy page; the detail carries no name."""
    act_as(manager)
    vacancy = await _create(client, budget_line, addressee_name=None)
    vid = vacancy["id"]

    async def row() -> dict:
        return next(v for v in (await client.get(BASE)).json() if v["id"] == vid)

    listed = await row()
    assert (listed["step"], listed["step_detail"]) == (
        "prepare",
        "Nog 1 gegeven in te vullen",
    )
    assert listed["step_since"] is not None

    await client.patch(f"{BASE}/{vid}", json={"addressee_name": "Fictief Directielid"})
    listed = await row()
    assert (listed["step"], listed["step_detail"]) == (
        "submit",
        "Klaar om aan te vragen",
    )

    act_as(beheerder)
    await _motivate(client, vid)
    await client.post(f"{BASE}/{vid}/submit", json={"requested_on": "2026-09-28"})
    listed = await row()
    assert (listed["step"], listed["step_detail"], listed["step_since"]) == (
        "decide",
        "Wacht op advies HR",
        "2026-09-28",
    )
    await _decide(
        client,
        vid,
        "hr_advice",
        person_name="Fictieve Adviseur",
        agreed=True,
        decided_on="2026-09-29",
    )
    listed = await row()
    assert (listed["step_detail"], listed["step_since"]) == (
        "Wacht op advies concern control",
        "2026-09-29",
    )
    await _decide(
        client,
        vid,
        "control_advice",
        person_name="Fictieve Controller",
        agreed=True,
        decided_on="2026-09-30",
    )
    assert (await row())["step_detail"] == "Wacht op akkoord"
    await _decide(
        client,
        vid,
        "approval",
        person_name="Fictief Directielid",
        agreed=True,
        decided_on="2026-10-01",
    )
    listed = await row()
    assert (listed["step"], listed["step_since"]) == ("open", "2026-10-01")
    assert "Fictie" not in json.dumps(
        {k: listed[k] for k in ("step", "step_detail", "step_since")}
    )

    response = await client.post(
        f"{BASE}/{vid}/texts", json={"kind": "vacancy_text", "body": "Tekst."}
    )
    text_id = response.json()["texts"][-1]["id"]
    await client.post(f"{BASE}/{vid}/texts/{text_id}/establish")
    await client.post(
        f"{BASE}/{vid}/publish",
        json={"channels": ["internal"], "opened_on": "2026-10-05"},
    )
    listed = await row()
    assert (listed["step"], listed["step_detail"]) == (
        "fill",
        "Interne openstelling loopt",
    )

    # Someone without a role sees the open vacancy, not where it stands.
    act_as(colleague)
    public = next(v for v in (await client.get(BASE)).json() if v["id"] == vid)
    assert not {"step", "step_detail", "step_since"} & public.keys()
