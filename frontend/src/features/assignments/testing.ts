/** Test helpers for the assignment screens. Fictional data only. */
import { vi } from 'vitest';
import type { AssignmentDetail, AssignmentPermissions } from './api';
import type { AssignmentFinance, Figures } from './financeApi';

/**
 * Answers fetch by path. A key matches when the request path starts with it;
 * the longest matching key wins. Unknown paths answer 404.
 */
export function mockApi(routes: Record<string, unknown>) {
  const keys = Object.keys(routes).sort((a, b) => b.length - a.length);
  const fetchMock = vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    const key = keys.find((candidate) => url.startsWith(candidate));
    if (key === undefined) {
      return Promise.resolve(
        new Response(JSON.stringify({ title: 'Niet gevonden', status: 404 }), {
          status: 404,
          headers: { 'Content-Type': 'application/problem+json' },
        }),
      );
    }
    return Promise.resolve(
      new Response(JSON.stringify(routes[key]), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

export const NO_PERMISSIONS: AssignmentPermissions = {
  edit_basic: false,
  edit_financial: false,
  edit_staffing: false,
  read_financial: false,
  read_staffing: false,
  read_roster: false,
};

/** What each kind of reader gets, as the backend decides it. */
export const PERMISSIONS = {
  owner: {
    edit_basic: true,
    edit_financial: true,
    edit_staffing: true,
    read_financial: true,
    read_staffing: true,
    read_roster: true,
  },
  planner: { ...NO_PERMISSIONS, edit_staffing: true, read_staffing: true, read_roster: true },
  member: { ...NO_PERMISSIONS, read_roster: true },
  lezer: { ...NO_PERMISSIONS, read_financial: true },
} satisfies Record<string, AssignmentPermissions>;

export function assignment(overrides: Partial<AssignmentDetail> = {}): AssignmentDetail {
  return {
    id: 'a1',
    uri: 'https://grip.example/id/opdracht/a1',
    name: 'Opdracht Alfa 2026',
    kind: 'external',
    status: 'in_progress',
    phase: 'active',
    status_since: '2026-01-05',
    client_organisation_id: 'o1',
    client_name: 'Voorbeeldministerie',
    start_date: '2026-01-01',
    end_date: '2026-12-31',
    owner_name: 'Voorbeeld Eigenaar',
    contractor_organisation_id: null,
    contractor_name: null,
    parent_assignment_uri: null,
    context_refs: [],
    client_contact: null,
    quote_date: null,
    notes: null,
    roles: [{ person_id: 'p0', name: 'Voorbeeld Eigenaar', role: 'owner' }],
    allowed_transitions: [],
    permissions: PERMISSIONS.owner,
    ...overrides,
  };
}

export const FIGURES: Figures = {
  budgeted_cents: 18780000,
  realised_cents: 2700000,
  planned_cents: 13500000,
  costs_realised_cents: 300000,
  costs_forecast_cents: 150000,
  costs_cents: 450000,
  expected_total_cents: 16650000,
  variance_cents: 2130000,
  variance_pct: '11.3',
  overrun: false,
  realised_total_cents: 3000000,
  realised_pct: '16.0',
};

export function finance(overrides: Partial<AssignmentFinance> = {}): AssignmentFinance {
  return {
    assignment_id: 'a1',
    name: 'Opdracht Alfa 2026',
    year: 2026,
    reference_month: '2026-02-01',
    key_figures: {
      agreed_cents: 19000000,
      budgeted_cents: 18780000,
      expected_total_cents: 16650000,
      agreed_minus_budgeted_cents: 220000,
      budgeted_minus_expected_cents: 2130000,
      realised_cents: 2700000,
      realised_pct: '16.0',
      delivered_cents: 1350000,
      to_deliver_cents: 1350000,
      invoiced_cents: 900000,
      to_invoice_cents: 450000,
    },
    totals: FIGURES,
    pricing_error: null,
    lines: [
      {
        budget_line_id: 'l1',
        description: 'Productmanager',
        kind: 'personnel',
        rate_category: 'D',
        figures: FIGURES,
        pricing_error: null,
        persons: [
          {
            allocation_id: 'x1',
            person_id: 'p1',
            person_name: 'Voorbeeld Een',
            start_date: '2026-01-01',
            end_date: '2026-12-31',
            realised_cents: 2700000,
            planned_cents: 13500000,
            total_cents: 16200000,
            category_mismatch: false,
          },
        ],
        persons_hidden: 0,
        costs: [
          {
            cost_item_id: 'c1',
            description: 'Hostingcontract',
            pct: '30',
            realised_cents: 300000,
            forecast_cents: 150000,
            total_cents: 450000,
          },
        ],
      },
    ],
    months: [
      {
        month: '2026-01-01',
        closed: true,
        budgeted_cents: 1440000,
        planned_cents: 1350000,
        realised_cents: 1350000,
        cumulative_budgeted_cents: 1440000,
        cumulative_realised_cents: 1350000,
        cumulative_planned_open_cents: 0,
        cumulative_expected_cents: 1350000,
        cumulative_variance_cents: 90000,
      },
      {
        month: '2026-03-01',
        closed: false,
        budgeted_cents: 1440000,
        planned_cents: 1350000,
        realised_cents: null,
        cumulative_budgeted_cents: 2880000,
        cumulative_realised_cents: 1350000,
        cumulative_planned_open_cents: 1350000,
        cumulative_expected_cents: 2700000,
        cumulative_variance_cents: 180000,
      },
    ],
    budgeted_outside_months_cents: 1500000,
    signals: [],
    free_room_threshold_pct: '10',
    ...overrides,
  };
}

/** Every attribute value and text in a rendered tree, for "no amount here" checks. */
export function allText(container: HTMLElement): string {
  const parts: string[] = [container.textContent ?? ''];
  for (const element of container.querySelectorAll('*')) {
    for (const attribute of element.getAttributeNames()) {
      parts.push(element.getAttribute(attribute) ?? '');
    }
  }
  return plain(parts.join('\n'));
}

/** Amounts are formatted with non-breaking spaces; tests compare with plain ones. */
export function plain(text: string | null | undefined): string {
  return (text ?? '').replace(/\u00a0|\u202f/g, ' ');
}
