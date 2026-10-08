import { screen, waitFor } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { PATHS } from "@/paths";
import { renderApp } from "@/test/utils";
import type { TextVersion, Vacancy, VacancyHire, VacancyOptions } from "./api";
import { VACANCY_TAB_SEGMENTS } from "./paths";
import { visibleTabs } from "./shell";
import {
  DecisionsTab,
  FulfilmentTab,
  ProcedureTab,
  RequestTab,
  TextTab,
} from "./tabs/VacancyTabs";
import { VacancyLayout } from "./VacancyLayout";

const OPTIONS: VacancyOptions = {
  vacancy_types: [{ value: "regulier", label: "Regulier" }],
  contract_types: [
    { value: "temporary_project", label: "Tijdelijk (projectcontract)" },
  ],
  statuses: [],
  channels: [{ value: "internal", label: "Intern" }],
  decision_kinds: [],
  text_kinds: [],
  steps: [],
  drafting_available: false,
  request_form_available: false,
  can_create_without_budget_line: false,
  can_manage_setup: false,
};

const NO_PERMISSIONS = {
  can_edit: false,
  can_record_hr_advice: false,
  can_record_control_advice: false,
  can_record_approval: false,
  can_download_form: false,
};

const MODEL_DRAFT: TextVersion = {
  id: "t-2",
  kind: "vacancy_text",
  body: "Concept van het model.",
  source: "model",
  model_id: "testmodel-1",
  prompt_version: "v1",
  created_at: "2026-10-02T09:00:00Z",
  model_assisted: true,
  origin_model_id: "testmodel-1",
  origin_drafted_at: "2026-10-02T09:00:00Z",
  is_current: false,
};

const OLDER: TextVersion = {
  id: "t-1",
  kind: "vacancy_text",
  body: "Eerdere versie.",
  source: "human",
  created_at: "2026-10-01T09:00:00Z",
  model_assisted: false,
  is_current: false,
};

const REQUESTED: Vacancy = {
  id: "v-1",
  function_title: "Backend-ontwikkelaar",
  scale: 11,
  fte: "0.80",
  status: "requested",
  declarable: true,
  vacancy_type: "regulier",
  contract_type: "temporary_project",
  channels: [],
  budget_line_id: "b-1",
  assignment_id: "a-1",
  assignment_name: "Opdracht Alfa",
  requested_on: "2026-09-28",
  has_openings: true,
  procedure: [
    {
      kind: "request",
      label: "Aanvraag",
      position: 1,
      recorded: true,
      started_on: "2026-09-28",
      ended_on: "2026-09-28",
    },
    {
      kind: "internal_opening",
      label: "Interne openstelling",
      position: 5,
      recorded: false,
      minimum_working_days: 5,
    },
  ],
  decisions: [
    {
      kind: "hr_advice",
      label: "Advies HR",
      person_name: "Fictieve Adviseur",
      has_account: true,
    },
  ],
  texts: [OLDER, MODEL_DRAFT],
  requester_name: "Fictieve Eigenaar",
  addressee_name: "Fictief Directielid",
  addressee_has_account: false,
  permissions: { ...NO_PERMISSIONS, can_edit: true, can_download_form: true },
};

const PUBLIC: Vacancy = {
  id: "v-2",
  function_title: "Productmanager",
  scale: 13,
  fte: "1.00",
  status: "open",
  published_at: "2026-10-05T08:00:00Z",
  published_text: {
    body: "Wij zoeken een productmanager.",
    established_at: "2026-10-02T08:00:00Z",
    model_assisted: true,
    model_id: "testmodel-1",
    drafted_at: "2026-10-01T08:00:00Z",
  },
  procedure: [],
  decisions: [],
  texts: [],
  permissions: NO_PERMISSIONS,
};

const HIRE: VacancyHire = {
  vacancy_id: "v-1",
  recruitment_ref: {
    system: "emply",
    reference: "V-2026-014",
    url: "https://werving.example/v/14",
  },
  hire: {
    person_id: "p-7",
    person_name: "Fictieve Collega",
    start_date: "2027-01-04",
    stage: "prospective",
  },
};

/** Answers GET requests from a table of path to body; anything else is a 404. */
function stubApi(routes: Record<string, unknown>) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input).split("?")[0] ?? "";
      if (path in routes) {
        return new Response(JSON.stringify(routes[path]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response(
        JSON.stringify({
          type: "about:blank",
          title: "Niet gevonden",
          status: 404,
        }),
        {
          status: 404,
          headers: { "Content-Type": "application/problem+json" },
        },
      );
    }),
  );
}

function renderVacancy(
  vacancy: Vacancy,
  tab = "",
  extra: Record<string, unknown> = {},
) {
  stubApi({
    [`/api/vacancies/${vacancy.id}`]: vacancy,
    "/api/vacancies/options": OPTIONS,
    [`/api/vacancies/${vacancy.id}/request-form/status`]: {
      available: true,
      file_name: "formulier.pdf",
      open_fields: [],
      motivation_established: false,
    },
    ...extra,
  });
  return renderApp(
    <Routes>
      <Route path={PATHS.vacancyDetail} element={<VacancyLayout />}>
        <Route index element={<RequestTab />} />
        <Route
          path={VACANCY_TAB_SEGMENTS.decisions}
          element={<DecisionsTab />}
        />
        <Route path={VACANCY_TAB_SEGMENTS.text} element={<TextTab />} />
        <Route
          path={VACANCY_TAB_SEGMENTS.procedure}
          element={<ProcedureTab />}
        />
        <Route
          path={VACANCY_TAB_SEGMENTS.fulfilment}
          element={<FulfilmentTab />}
        />
      </Route>
    </Routes>,
    { path: `/vacatures/${vacancy.id}${tab ? `/${tab}` : ""}` },
  );
}

const primaryOnPage = (container: HTMLElement) =>
  [...container.querySelectorAll('nldd-button[appearance="primary"]')].map(
    (button) => button.getAttribute("text"),
  );

const tabsOf = (container: HTMLElement) =>
  [...container.querySelectorAll("nldd-tab-bar-item")].map((tab) => [
    tab.getAttribute("text"),
    tab.hasAttribute("current"),
  ]);

afterEach(() => {
  vi.unstubAllGlobals();
});

/** Position (from 1) of the step the bar marks as current. */
function currentStep(container: HTMLElement): number {
  const items = [...container.querySelectorAll("nldd-step-bar-item")];
  return (
    items.findIndex((item) => item.getAttribute("status") === "current") + 1
  );
}

describe("the header of a vacancy", () => {
  it("says what it is, where it belongs and where it stands, with one primary action", async () => {
    const { container } = renderVacancy(REQUESTED);
    await waitFor(() =>
      expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
        "Backend-ontwikkelaar",
      ),
    );
    expect(container.querySelector("nldd-badge")?.getAttribute("text")).toBe(
      "Aangevraagd",
    );
    // The assignment links to its Bemensing tab.
    expect(
      container
        .querySelector('nldd-link[text="Opdracht Alfa"]')
        ?.getAttribute("href"),
    ).toBe("/opdrachten/a-1/bemensing");
    expect(container.textContent).toContain("Regulier · Schaal 11, 0,8 fte");
    expect(currentStep(container)).toBe(3);
    expect(tabsOf(container)).toEqual([
      ["Aanvraag", true],
      ["Taken", false],
      ["Advies en akkoord", false],
      ["Tekst", false],
      ["Procedure", false],
      ["Vervulling", false],
    ]);
    // The step is done on another tab: the one primary action leads there.
    expect(primaryOnPage(container)).toEqual(["Naar advies en akkoord"]);
    expect(container.querySelectorAll("h1")).toHaveLength(1);
  });

  it("leaves out the tab a reader has nothing on", () => {
    expect(visibleTabs(REQUESTED)).toContain("fulfilment");
    const reader = { ...REQUESTED, permissions: NO_PERMISSIONS };
    expect(visibleTabs(reader)).toEqual([
      "request",
      "tasks",
      "decisions",
      "text",
      "procedure",
    ]);
    expect(visibleTabs(PUBLIC)).toEqual([]);
  });

  it("shows the published text and nothing to do to someone without a role", async () => {
    const { container } = renderVacancy(PUBLIC);
    await waitFor(() =>
      expect(container.textContent).toContain("Wij zoeken een productmanager."),
    );
    expect(container.textContent).toContain("Een taalmodel (testmodel-1)");
    expect(container.querySelector("nldd-tab-bar")).toBeNull();
    expect(container.querySelector("nldd-step-bar")).toBeNull();
    expect(container.querySelector("nldd-button")).toBeNull();
    expect(document.body.querySelector("nldd-sheet")).toBeNull();
  });

  it("says so when the vacancy is not there or not visible", async () => {
    stubApi({ "/api/vacancies/options": OPTIONS });
    const { container } = renderApp(
      <Routes>
        <Route path={PATHS.vacancyDetail} element={<VacancyLayout />} />
      </Routes>,
      { path: "/vacatures/v-9" },
    );
    await waitFor(() =>
      expect(
        container
          .querySelector('nldd-banner[variant="critical"]')
          ?.getAttribute("text"),
      ).toBe("Deze vacature bestaat niet, of je kunt haar niet inzien."),
    );
  });

  it("carries the one primary action when the vacancy is approved", async () => {
    const approved: Vacancy = { ...REQUESTED, status: "approved" };
    const { container } = renderVacancy(approved, "procedure");
    await waitFor(() =>
      expect(
        container.querySelector(
          'nldd-table[accessible-label="Stappen van de procedure"]',
        ),
      ).not.toBeNull(),
    );
    // "Stel open" once, in the header; the procedure tab has no primary of its own.
    expect(primaryOnPage(container)).toEqual(["Stel open"]);
    expect(
      container.querySelectorAll('nldd-button[text="Stel open"]'),
    ).toHaveLength(1);
  });
});

describe("the Aanvraag tab", () => {
  it("lists what the form asks for, filled or visibly not, each the way to fill it", async () => {
    const draft: Vacancy = {
      ...REQUESTED,
      status: "draft",
      contract_type: null,
      scale_fits_budget_line: false,
      budget_line_scales: [12, 13],
    };
    const { container } = renderVacancy(draft);
    await waitFor(() =>
      expect(
        container.querySelector(
          'nldd-list[accessible-label="Gegevens voor het aanvraagformulier"]',
        ),
      ).not.toBeNull(),
    );
    const rows = [
      ...container.querySelectorAll(
        'nldd-list[accessible-label="Gegevens voor het aanvraagformulier"] nldd-list-item',
      ),
    ].map((row) => {
      const cells = [...row.querySelectorAll("nldd-text-cell")];
      return [
        cells[0]!.getAttribute("text"),
        cells[1]!.getAttribute("text"),
        row.querySelector("nldd-icon-cell")!.getAttribute("icon"),
        row.hasAttribute("button") || row.hasAttribute("href"),
      ];
    });
    expect(rows).toEqual([
      ["FGR-functienaam", "Nog niet ingevuld", "circle", true],
      ["Schaal", "11", "check-circle-filled", true],
      ["Type contract", "Nog niet ingevuld", "circle", true],
      ["Aan", "Fictief Directielid", "check-circle-filled", true],
      ["Aanleiding en motivatie", "Nog niet ingevuld", "circle", true],
    ]);
    // A fresh vacancy: the step bar is at 1 and carries the primary action.
    expect(currentStep(container)).toBe(1);
    expect(primaryOnPage(container)).toEqual(["Bereid aanvraag voor"]);
    expect(
      container
        .querySelector('nldd-banner[variant="warning"]')
        ?.getAttribute("text"),
    ).toContain(
      "Schaal 11 valt buiten de tariefcategorie van de begrotingsregel",
    );
    await waitFor(() =>
      expect(
        container
          .querySelector('nldd-button[text="Download aanvraagformulier (pdf)"]')
          ?.getAttribute("href"),
      ).toBe("/api/vacancies/v-1/request-form"),
    );
  });

  it("has no row for the addressee and nothing to edit for a reader without names", async () => {
    const reader: Vacancy = { ...REQUESTED, permissions: NO_PERMISSIONS };
    delete reader.addressee_name;
    delete reader.addressee_has_account;
    const { container } = renderVacancy(reader);
    await waitFor(() =>
      expect(container.querySelector("nldd-list")).not.toBeNull(),
    );
    const labels = [
      ...container.querySelectorAll("nldd-list nldd-list-item"),
    ].map((row) => row.querySelector("nldd-text-cell")!.getAttribute("text"));
    expect(labels).not.toContain("Aan");
    expect(container.querySelector("nldd-list-item[button]")).toBeNull();
    expect(
      container.querySelector(
        'nldd-button[text="Wijzig functie, fte of periode"]',
      ),
    ).toBeNull();
    expect(tabsOf(container).map(([text]) => text)).not.toContain("Vervulling");
  });
});

describe("the Advies en akkoord tab", () => {
  it("shows the three decisions in columns and makes the next one to record primary", async () => {
    const adviser: Vacancy = {
      ...REQUESTED,
      permissions: { ...NO_PERMISSIONS, can_record_hr_advice: true },
    };
    const { container } = renderVacancy(adviser, "advies");
    await waitFor(() =>
      expect(
        container.querySelector(
          'nldd-table[accessible-label="Advies en akkoord"]',
        ),
      ).not.toBeNull(),
    );
    const rows = [
      ...container.querySelectorAll("nldd-table-row:not([slot])"),
    ].map((row) =>
      [...row.querySelectorAll("nldd-text-cell")].map((cell) =>
        cell.getAttribute("text"),
      ),
    );
    expect(rows).toEqual([
      ["Advies HR", "Nog geen besluit", "Fictieve Adviseur"],
      ["Advies concern control", "Nog niemand genoemd", ""],
      ["Akkoord", "Nog niemand genoemd", ""],
    ]);
    // On the tab of the current step the header has no button; the tab has the one.
    expect(primaryOnPage(container)).toEqual(["Leg vast"]);
    expect(tabsOf(container).find(([, current]) => current)?.[0]).toBe(
      "Advies en akkoord",
    );
  });
});

describe("the Tekst tab", () => {
  it("shows the newest version with its origin and keeps earlier ones closed", async () => {
    const { container } = renderVacancy(REQUESTED, "tekst");
    await waitFor(() =>
      expect(container.textContent).toContain("Concept van het model."),
    );
    expect(container.textContent).toContain(
      "Opgesteld door een taalmodel (testmodel-1)",
    );
    expect(container.textContent).not.toContain("Eerdere versie.");
    expect(
      container.querySelector('nldd-button[text="Toon eerdere versies (1)"]'),
    ).not.toBeNull();
    expect(
      container.querySelector('nldd-button[text="Stel vast"]'),
    ).not.toBeNull();
    // No model is set up: drafting is not offered, and nothing says so.
    expect(
      container.querySelector('nldd-button[text="Laat een concept opstellen"]'),
    ).toBeNull();
    expect(container.textContent).not.toContain("niet ingesteld");
    expect(
      [...container.querySelectorAll('nldd-title[heading-level="2"]')].map(
        (el) => el.getAttribute("text"),
      ),
    ).toEqual(["Vacaturetekst", "Aanleiding en motivatie"]);
  });

  it("offers drafting when the model is set up", async () => {
    const { container } = renderVacancy(REQUESTED, "tekst", {
      "/api/vacancies/options": { ...OPTIONS, drafting_available: true },
    });
    await waitFor(() =>
      expect(
        container.querySelectorAll(
          'nldd-button[text="Laat een concept opstellen"]',
        ),
      ).toHaveLength(2),
    );
  });
});

describe("the Procedure tab", () => {
  it("shows the steps with their dates and the minimum before it starts", async () => {
    const { container } = renderVacancy(REQUESTED, "procedure");
    await waitFor(() =>
      expect(
        container.querySelector(
          'nldd-text-cell[text="5. Interne openstelling"]',
        ),
      ).not.toBeNull(),
    );
    expect(
      container
        .querySelector('nldd-text-cell[text="5. Interne openstelling"]')
        ?.getAttribute("supporting-text"),
    ).toBe("Duurt minimaal 5 werkdagen");
    expect(
      container.querySelector('nldd-text-cell[text="Nog niet gestart"]'),
    ).not.toBeNull();
  });
});

describe("the Vervulling tab", () => {
  it("shows the reference in the recruitment system and who was hired, with links", async () => {
    const filled: Vacancy = { ...REQUESTED, status: "filled" };
    const { container } = renderVacancy(filled, "vervulling", {
      "/api/vacancies/v-1/hire": HIRE,
    });
    await waitFor(() =>
      expect(
        container.querySelector('nldd-link[text="Fictieve Collega"]'),
      ).not.toBeNull(),
    );
    expect(
      container
        .querySelector('nldd-link[text="Fictieve Collega"]')
        ?.getAttribute("href"),
    ).toBe("/team/p-7");
    expect(
      container
        .querySelector('nldd-link[text="V-2026-014"]')
        ?.getAttribute("href"),
    ).toBe("https://werving.example/v/14");
    expect(
      container.querySelector('nldd-text-cell[text="Emply"]'),
    ).not.toBeNull();
    expect(
      container.querySelector('nldd-text-cell[text="4 jan 2027"]'),
    ).not.toBeNull();
    expect(
      container
        .querySelector('nldd-link[text="Bemensing van Opdracht Alfa"]')
        ?.getAttribute("href"),
    ).toBe("/opdrachten/a-1/bemensing");
    // Candidates are not kept here; one quiet line says where they are.
    expect(container.textContent).toContain(
      "Kandidaten staan in het wervingssysteem; grip bewaart ze niet.",
    );
    expect(
      container.querySelector('nldd-button[text="Aanname gaat niet door"]'),
    ).not.toBeNull();
    // Filled: no step bar and no primary action left.
    expect(container.querySelector("nldd-step-bar")).toBeNull();
    expect(primaryOnPage(container)).toEqual([]);
  });

  it("offers to fill an open vacancy from the step bar, once", async () => {
    const open: Vacancy = {
      ...REQUESTED,
      status: "open",
      permissions: {
        ...REQUESTED.permissions,
        can_fill: true,
        can_withdraw: true,
      },
    };
    const { container } = renderVacancy(open, "vervulling", {
      "/api/vacancies/v-1/hire": {
        vacancy_id: "v-1",
        recruitment_ref: null,
        hire: null,
      },
    });
    await waitFor(() =>
      expect(
        container.querySelector('nldd-button[text="Leg verwijzing vast"]'),
      ).not.toBeNull(),
    );
    expect(primaryOnPage(container)).toEqual(["Vervul"]);
    expect(
      container.querySelectorAll('nldd-button[text="Vervul"]'),
    ).toHaveLength(1);
    expect(container.textContent).toContain(
      "Nog niemand aangenomen voor 0,8 fte",
    );
    expect(
      container.querySelector('nldd-button[text="Trek vacature in"]'),
    ).not.toBeNull();
    // The hire sheet asks who and from when; it is in the document, closed.
    const hire = [...document.body.querySelectorAll("nldd-sheet")].find(
      (sheet) =>
        sheet
          .querySelector("nldd-top-title-bar")
          ?.getAttribute("text")
          ?.includes("vervullen"),
    )!;
    expect(hire.hasAttribute("open")).toBe(false);
    expect(
      [...hire.querySelectorAll("nldd-form-field")].map((field) =>
        field.getAttribute("label"),
      ),
    ).toEqual(["Naam van de nieuwe collega", "Start op"]);
    expect(
      hire.querySelector("nldd-checkbox-field")?.getAttribute("label"),
    ).toBe("Plan de inzet meteen op de begrotingsregel");
  });
});
