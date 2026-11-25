import { act, fireEvent, waitFor } from '@testing-library/react';
import { StrictMode, useEffect } from 'react';
import { Route, Routes, useNavigate } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { allText, plain } from '@/features/assignments/testing';
import { AssignmentHistoryTab } from '@/features/history/History';
import { renderApp } from '@/test/utils';
import type {
  Moment,
  Stand,
  StandAcceptance,
  StandApproval,
  StandBudgetLine,
  StandQuote,
} from './api';
import { chronicleKeys, momentOf } from './api';
import {
  acceptanceTold,
  approvalTold,
  budgetLineSummary,
  laterKnownText,
  momentByline,
  offerTold,
  restatedText,
  standQuoteLabel,
  standTitle,
} from './words';

afterEach(() => vi.unstubAllGlobals());

const HASH = 'b'.repeat(64);
const FILE_HASH = 'c'.repeat(64);

const MADE: Moment = {
  seq: 3,
  occurred_at: '2026-11-01T09:00:00Z',
  fact: 'quote_issued',
  title: 'Offerte gemaakt',
  decision: true,
  actor_name: 'Anna Voorbeeld',
  actor_kind: 'person',
  effective_on: '2026-11-01',
  statement: 'Offerte VG-2026-0007 gemaakt, € 120.000.',
  lines: [],
  erased: false,
};

const CHANGED: Moment = {
  seq: 7,
  occurred_at: '2026-11-03T13:02:00Z',
  fact: 'budget_line_changed',
  title: 'Begrotingsregel gewijzigd',
  decision: false,
  actor_name: 'Anna Voorbeeld',
  actor_kind: 'person',
  effective_on: '2026-10-30',
  statement: 'Begrotingsregel Productmanager gewijzigd.',
  lines: [],
  erased: false,
};

const SIGNED: Moment = {
  seq: 9,
  occurred_at: '2026-11-10T10:00:00Z',
  fact: 'quote_accepted',
  title: 'Offerte getekend',
  decision: false,
  actor_name: 'Anna Voorbeeld',
  actor_kind: 'person',
  effective_on: '2026-11-02',
  statement:
    'Anna Voorbeeld legde vast dat Bert Voorbeeld op 2 november 2026 tekende, met een getekende pdf.',
  lines: [],
  erased: false,
};

const COURSE = {
  key: 'akkoord',
  label: 'Naar een akkoord',
  steps: [
    { key: 'begroting', label: 'Begroting', state: 'done' as const },
    { key: 'offerte', label: 'Offerte', state: 'current' as const },
    { key: 'akkoord', label: 'Akkoord', state: 'future' as const },
  ],
  next: {
    mine: false,
    part: 'watches' as const,
    headline: 'De offerte',
    sentence: 'De eigenaar is aan zet: de offerte.',
  },
};

const ASSIGNMENT = {
  name: 'Opdracht Alfa 2026',
  status: 'quoted',
  status_label: 'Offerte gemaakt',
  kind: 'external',
  owner_name: 'Anna Voorbeeld',
  client_name: 'Voorbeeldministerie',
  start_date: '2026-01-01',
  end_date: '2026-12-31',
  notes: null,
  quote_date: null,
  verbal_agreement_note: null,
};

const CONTENT = {
  name: 'Opdracht Alfa 2026',
  lines: [
    { position: 1, description: 'Productmanager', kind: 'personnel', amount_cents: 12000000 },
  ],
  subtotals_per_year: [{ year: 2026, amount_cents: 12000000 }],
  total_cents: 12000000,
};

/** What every quote holds for a reader of class B, whatever became of it. */
const QUOTE_VALUES = {
  changed: false,
  total_cents: 12000000,
  valid_until: null,
  issued_at: '2026-10-01T09:00:00Z',
  snapshot_hash: HASH,
  document_sha256: null,
  has_document: false,
  approvals: [],
  offers: [],
  acceptance: null,
  rejection: null,
  content: CONTENT,
};

/** A moment with everything a reader with all classes gets. */
const FULL: Stand = {
  moment: CHANGED,
  previous_seq: 3,
  next_seq: 9,
  assignment: { ...ASSIGNMENT, quoted_amount_cents: 12000000 },
  course: COURSE,
  outside: ['De tarieven zijn gewijzigd.'],
  outside_values: ['Tarief van categorie A op Tarieven 2027 gewijzigd.'],
  restated: [],
  later_known: [
    {
      seq: 9,
      title: 'Offerte getekend',
      statement: SIGNED.statement!,
      effective_on: '2026-11-02',
    },
  ],
  budget: {
    lines: [
      {
        id: 'l1',
        description: 'Productmanager',
        kind: 'personnel',
        position: 1,
        role: 'Productmanager',
        fte: '0.8',
        start_date: '2026-01-01',
        end_date: '2026-12-31',
        rate_category: 'D',
        budgeted_cents: 12000000,
        change: 'changed',
      },
      {
        id: 'l2',
        description: 'Reiskosten',
        kind: 'fixed',
        position: 2,
        year: 2026,
        amount_cents: 500000,
        budgeted_cents: 500000,
        change: 'added',
      },
      {
        id: 'l3',
        description: 'Developer',
        kind: 'personnel',
        position: 3,
        budgeted_cents: 300000,
        change: null,
      },
    ],
    removed: ['Tester'],
    subtotals_by_year: { '2026': 8000000, '2027': 4800000 },
    total_budgeted_cents: 12800000,
    previous_total_cents: 12000000,
    pricing_error: null,
  },
  quotes: [
    {
      ...QUOTE_VALUES,
      id: 'q0',
      reference: 'VG-2026-0005',
      status: 'superseded',
      status_label: 'Vervangen',
      total_cents: 9000000,
    },
    {
      ...QUOTE_VALUES,
      id: 'q2',
      reference: 'VG-2026-0008',
      status: 'rejected',
      status_label: 'Afgewezen',
      total_cents: 7000000,
      rejection: {
        reason: 'Te duur',
        rejected_at: '2026-10-20T12:00:00Z',
        recorded_by_name: 'Anna Voorbeeld',
      },
    },
    {
      id: 'q1',
      reference: 'VG-2026-0007',
      status: 'accepted',
      status_label: 'Akkoord',
      changed: true,
      total_cents: 12000000,
      valid_until: '2026-12-31',
      issued_at: '2026-11-01T09:00:00Z',
      snapshot_hash: HASH,
      document_sha256: FILE_HASH,
      has_document: true,
      approvals: [
        {
          status: 'approved',
          requested_by_name: 'Anna Voorbeeld',
          requested_at: '2026-11-01T10:00:00Z',
          decided_by_name: 'Carla Voorbeeld',
          decided_at: '2026-11-01T11:00:00Z',
          withdrawn_by_name: null,
          withdrawn_at: null,
          request_note: null,
          decision_note: 'Akkoord met de uren',
          self_approved: false,
        },
      ],
      offers: [
        {
          channel: 'document',
          recipient: null,
          offered_at: '2026-11-02T09:00:00Z',
          offered_by_name: 'Anna Voorbeeld',
          invitation: null,
        },
      ],
      acceptance: {
        signer_name: 'Bert Voorbeeld',
        form: 'uploaded_pdf',
        signed_at: '2026-11-02T12:00:00Z',
        organisation_name: 'Voorbeeldministerie',
        recorded_by_name: 'Anna Voorbeeld',
      },
      rejection: null,
      content: CONTENT,
    },
  ],
  incomplete: false,
};

/** A reader of class A only: every other field is absent from the answer, not null. */
const CLASS_A: Stand = {
  moment: {
    seq: 7,
    occurred_at: CHANGED.occurred_at,
    fact: CHANGED.fact,
    title: 'Begrotingsregel gewijzigd',
    decision: false,
    actor_name: 'Anna Voorbeeld',
    actor_kind: 'person',
    erased: false,
  },
  previous_seq: 3,
  next_seq: null,
  assignment: ASSIGNMENT,
  course: COURSE,
  outside: ['De tarieven zijn gewijzigd.'],
  restated: [],
  later_known: [{ seq: 9, title: 'Offerte getekend' }],
  budget: {
    lines: [
      {
        id: 'l1',
        description: 'Productmanager',
        kind: 'personnel',
        position: 1,
        change: 'changed',
      },
    ],
    removed: [],
  },
  quotes: [
    {
      id: 'q1',
      reference: 'VG-2026-0007',
      status: 'issued',
      status_label: 'Offerte gemaakt',
      changed: true,
    },
  ],
  incomplete: false,
};

/** Answers by the exact path, so a moment without an entry is a 404 as on the server. */
function stubApi(routes: Record<string, unknown>) {
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input).split('?')[0]!;
    const reply = routes[init?.method === 'POST' ? `POST ${path}` : path];
    return Promise.resolve(
      new Response(JSON.stringify(reply ?? { title: 'Niet gevonden', status: 404 }), {
        status: reply === undefined ? 404 : 200,
        headers: {
          'Content-Type': reply === undefined ? 'application/problem+json' : 'application/json',
        },
      }),
    );
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

let navigateTo: (path: string) => void = () => {};

function HoldNavigate() {
  const navigate = useNavigate();
  useEffect(() => {
    navigateTo = navigate;
  }, [navigate]);
  return null;
}

function renderTab(
  path: string,
  {
    moments = [MADE, CHANGED, SIGNED],
    stand,
    laterStand,
    strict = false,
    extra = {},
  }: {
    moments?: Moment[];
    stand?: Stand;
    laterStand?: Stand;
    strict?: boolean;
    extra?: Record<string, unknown>;
  } = {},
) {
  const fetchMock = stubApi({
    '/api/assignments/a1/chronicle': { items: moments },
    ...(stand ? { '/api/assignments/a1/chronicle/7': stand } : {}),
    ...(laterStand ? { '/api/assignments/a1/chronicle/9': laterStand } : {}),
    '/api/events': { items: [], next_before: null },
    ...extra,
  });
  const tab = (
    <>
      <HoldNavigate />
      <Routes>
        <Route path="/opdrachten/:assignmentId/geschiedenis" element={<AssignmentHistoryTab />} />
      </Routes>
    </>
  );
  const view = renderApp(strict ? <StrictMode>{tab}</StrictMode> : tab, { path });
  return { ...view, fetchMock };
}

const requests = (fetchMock: ReturnType<typeof stubApi>) =>
  (fetchMock.mock.calls as unknown[][]).map((call) => String(call[0]));

/** What a reader meets, top to bottom: the text of each element and its `text` attribute. */
function reading(container: HTMLElement): string {
  return [...container.querySelectorAll('*')]
    .map((element) => {
      const own = [...element.childNodes]
        .filter((node) => node.nodeType === Node.TEXT_NODE)
        .map((node) => node.textContent)
        .join('');
      return `${element.getAttribute('text') ?? ''}${own}`;
    })
    .filter(Boolean)
    .join('\n');
}

const HEADING = 'Stand op 3 november 2026, 14:02';

/** What holds focus has this inside it. The body holds everything, so it does not count. */
function focused(selector: string): Element | null {
  const active = document.activeElement;
  return active === document.body ? null : (active?.querySelector(selector) ?? null);
}

describe('the tab Geschiedenis of an assignment', () => {
  it('opens on the moments, oldest first, with a choice of what to show', async () => {
    const { container, fetchMock } = renderTab('/opdrachten/a1/geschiedenis');
    await waitFor(() => expect(container.querySelector('nldd-list-item')).not.toBeNull());
    expect(container.querySelector('select')).toHaveValue('momenten');
    expect([...container.querySelectorAll('option')].map((option) => option.textContent)).toEqual([
      'Momenten',
      'Wijzigingen',
    ]);
    const rows = [...container.querySelectorAll('nldd-list-item')];
    expect(rows.map((row) => row.getAttribute('href'))).toEqual([
      '/opdrachten/a1/geschiedenis?moment=3',
      '/opdrachten/a1/geschiedenis?moment=7',
      '/opdrachten/a1/geschiedenis?moment=9',
    ]);
    expect(
      [...container.querySelectorAll('nldd-step-cell')].map((cell) =>
        cell.getAttribute('position'),
      ),
    ).toEqual(['first', 'between', 'last']);
    // Each row one line with one quiet line under it, the mark only on a decision.
    const cell = rows[1]!.querySelector('nldd-text-cell');
    expect(cell).toHaveAttribute('text', CHANGED.statement);
    expect(plain(cell?.getAttribute('supporting-text'))).toContain(' · Anna Voorbeeld');
    expect(rows[0]!.querySelector('nldd-badge')).toHaveAttribute('text', 'Besluit');
    expect(rows[1]!.querySelector('nldd-badge')).toBeNull();
    expect(container.querySelector('nldd-title')).toBeNull();
    expect(requests(fetchMock).some((url) => url.startsWith('/api/events'))).toBe(false);
  });

  it('keeps the existing list under Wijzigingen, in the address', async () => {
    const { container, fetchMock } = renderTab('/opdrachten/a1/geschiedenis?toon=wijzigingen');
    await waitFor(() =>
      expect(container.querySelector('[text="Nog niets gebeurd"]')).not.toBeNull(),
    );
    expect(container.querySelector('select')).toHaveValue('wijzigingen');
    expect(container.querySelector('nldd-list-item')).toBeNull();
    expect(requests(fetchMock).some((url) => url.startsWith('/api/events'))).toBe(true);
  });

  it('shows an old case without moments the existing list, without the choice', async () => {
    const { container } = renderTab('/opdrachten/a1/geschiedenis', { moments: [] });
    await waitFor(() =>
      expect(container.querySelector('[text="Nog niets gebeurd"]')).not.toBeNull(),
    );
    expect(container.querySelector('select')).toBeNull();
  });
});

const APPROVAL_ROW: StandApproval = {
  status: 'requested',
  requested_by_name: 'Anna Voorbeeld',
  requested_at: '2026-11-01T10:00:00Z',
  decided_by_name: null,
  decided_at: null,
  withdrawn_by_name: null,
  withdrawn_at: null,
  request_note: null,
  decision_note: null,
  self_approved: false,
};

describe('how things stood at a moment', () => {
  const opened = async (stand: Stand, moments?: Moment[]) => {
    const view = renderTab('/opdrachten/a1/geschiedenis?moment=7', {
      stand,
      ...(moments ? { moments } : {}),
    });
    await waitFor(() =>
      expect(view.container.querySelector(`nldd-title[text="${HEADING}"]`)).not.toBeNull(),
    );
    return view;
  };

  it('shows a moment with all its fields, in the order of the screen', async () => {
    const { container } = await opened(FULL);
    const text = allText(container);
    // The fact.
    expect(container.textContent).toContain(CHANGED.statement);
    // The course as it was, with no button and no way to act.
    expect(text).toContain('De eigenaar is aan zet: de offerte.');
    expect(text).toContain('Eigenaar: Anna Voorbeeld');
    expect(container.querySelector('nldd-step-bar')).toHaveAttribute(
      'accessible-label',
      expect.stringContaining('Verloop op 3 nov 2026'),
    );
    expect(container.querySelector('nldd-button')).toBeNull();
    // The budget, with what changed marked in place.
    const rows = [
      ...container.querySelectorAll(
        'nldd-table[accessible-label="Begrotingsregels"] nldd-table-row',
      ),
    ];
    const marks = rows.map((row) => row.querySelector('nldd-badge')?.getAttribute('text') ?? null);
    expect(marks.slice(1, 4)).toEqual(['Gewijzigd', 'Nieuw', null]);
    expect(text).toContain('0,8 FTE');
    expect(text).toContain('Verwijderd: Tester');
    expect(text).toContain('Totaal begroot');
    expect(text).toContain('€ 128.000');
    expect(text).toContain('was € 120.000');
    expect(text).toContain('Subtotaal 2027');
    // The quote this moment changed first; the replaced one in a quiet line.
    const badges = [...container.querySelectorAll('nldd-badge')].map((badge) =>
      badge.getAttribute('text'),
    );
    expect(badges.filter((badge) => badge === 'Akkoord' || badge === 'Afgewezen')).toEqual([
      'Akkoord',
      'Afgewezen',
    ]);
    expect(badges).not.toContain('Vervangen');
    expect(text).toContain('Vervangen: VG-2026-0005 (€ 90.000)');
    expect(text).toContain('Offertebedrag');
    expect(text).toContain('Geldig t/m');
    expect(text).toContain('Echtheidskenmerk');
    expect(text).toContain(`${HASH.slice(0, 12)}…`);
    expect(text).not.toContain(HASH);
    expect(text).toContain('Intern goedgekeurd op');
    expect(text).toContain('door Carla Voorbeeld');
    expect(text).toContain('Akkoord met de uren');
    expect(text).toContain('Als document');
    expect(text).toContain('Getekend op 2 nov 2026 door Bert Voorbeeld namens Voorbeeldministerie');
    expect(text).toContain('Getekende pdf vastgelegd door Anna Voorbeeld');
    expect(text).toContain('Afgewezen op 20 okt 2026: Te duur');
    expect(container.querySelector('nldd-link[text="Bekijk pdf"]')).toHaveAttribute(
      'href',
      '/api/quotes/q1/document',
    );
    expect(
      container.querySelector('nldd-table[accessible-label="Regels van Offerte VG-2026-0007"]'),
    ).not.toBeNull();
    const read = reading(container);
    const order = [
      HEADING,
      CHANGED.statement!,
      'Tarief van categorie A',
      'Later vastgelegd',
      'De eigenaar is aan zet',
      'Opdrachtgever',
      'Totaal begroot',
      'Offerte VG-2026-0007',
      'Offerte VG-2026-0008',
      'Vervangen:',
      'Vorige',
      'Volgende',
      'Terug naar nu',
    ].map((word) => read.indexOf(word));
    expect(order.every((position) => position >= 0)).toBe(true);
    expect(order).toEqual([...order].sort((a, b) => a - b));
    // The word also stands in the choice above the stand; the list comes last.
    expect(read.lastIndexOf('Momenten')).toBeGreaterThan(read.indexOf('Terug naar nu'));
  });

  it('says the day a quote was made: a received one names it nowhere else', async () => {
    const { container } = await opened(FULL);
    const text = plain(allText(container));
    expect(text).toContain('Gemaakt');
    expect(text).toContain('1 okt 2026');
  });

  it('does not say the role of a quote line under a name that starts with it', async () => {
    const line = CONTENT.lines[0]!;
    const { container } = await opened({
      ...FULL,
      quotes: [
        {
          ...FULL.quotes.at(-1)!,
          content: {
            ...CONTENT,
            lines: [
              { ...line, description: 'Ontwerper: Zoë "#2" & co', role: 'ontwerper' },
              { ...line, position: 2, description: 'Kernteam', role: 'Ontwerper' },
            ],
          },
        },
      ],
    });
    const under = [...container.querySelectorAll('nldd-text-cell[hide-below="md"]')]
      .filter((cell) =>
        ['Ontwerper: Zoë "#2" & co', 'Kernteam'].includes(cell.getAttribute('text') ?? ''),
      )
      .map((cell) => cell.getAttribute('supporting-text'));
    expect(under).toEqual([null, 'Ontwerper']);
  });

  it('says once what a row of the stand says', async () => {
    const [line, ...lines] = FULL.budget!.lines;
    const signed = FULL.quotes.at(-1)!;
    const { container } = await opened({
      ...FULL,
      budget: {
        ...FULL.budget!,
        lines: [
          {
            ...line!,
            role: 'Standards engineer',
            description: 'Standards engineer: coördinatie "#2" & co',
          },
          ...lines,
        ],
      },
      quotes: [
        {
          ...signed,
          acceptance: {
            signer_name: 'Tekenaar Voorbeeld',
            form: 'signing_link',
            signed_at: '2026-10-31T12:00:00Z',
            organisation_name: 'Voorbeeldministerie',
            recorded_by_name: 'Tekenaar Voorbeeld',
          },
        },
      ],
    });
    const count = (word: RegExp) => reading(container).match(word)?.length ?? 0;
    expect(count(/Standards engineer/g)).toBe(1);
    expect(count(/Tekenaar Voorbeeld/g)).toBe(1);
    expect(count(/aangeboden/gi)).toBe(1);
    // What stays: how it was signed, and the rest of the line.
    expect(allText(container)).toContain('Getekend via de tekenlink');
    expect(allText(container)).toContain('0,8 FTE');
  });

  it('walks by links, and back to now is the tab without a moment', async () => {
    const { container } = await opened(FULL);
    const link = (text: string) => container.querySelector(`nldd-link[text="${text}"]`);
    expect(link('Vorige')).toHaveAttribute('href', '/opdrachten/a1/geschiedenis?moment=3');
    expect(link('Volgende')).toHaveAttribute('href', '/opdrachten/a1/geschiedenis?moment=9');
    expect(link('Terug naar nu')).toHaveAttribute('href', '/opdrachten/a1/geschiedenis');
    const current = container.querySelectorAll('nldd-list-item[current]');
    expect(current).toHaveLength(1);
    expect(current[0]).toHaveAttribute('href', '/opdrachten/a1/geschiedenis?moment=7');
    expect(
      [...container.querySelectorAll('nldd-step-cell')].map((cell) => cell.getAttribute('status')),
    ).toEqual(['past', 'current', 'future']);
  });

  it('moves focus to the heading after a step, not on arrival, and keeps the old stand meanwhile', async () => {
    const { container } = renderTab('/opdrachten/a1/geschiedenis?moment=7', {
      stand: FULL,
      laterStand: { ...FULL, moment: SIGNED, previous_seq: 7, next_seq: null },
    });
    const title = (text: string) => container.querySelector(`nldd-title[text="${text}"]`);
    await waitFor(() => expect(title(HEADING)).not.toBeNull());
    expect(document.activeElement).toBe(document.body);

    act(() => navigateTo('/opdrachten/a1/geschiedenis?moment=9'));
    expect(title(HEADING)).not.toBeNull();
    expect(container.querySelector('[data-state="loading"]')).toBeNull();

    const later = standTitle(SIGNED.occurred_at);
    await waitFor(() => expect(title(later)).not.toBeNull());
    await waitFor(() => expect(focused('nldd-title')).toBe(title(later)));
  });

  describe('where focus goes', () => {
    const heldFrames = () => {
      const frames: FrameRequestCallback[] = [];
      vi.stubGlobal('requestAnimationFrame', (frame: FrameRequestCallback) => frames.push(frame));
      return () => act(() => frames.splice(0).forEach((frame) => frame(0)));
    };
    const LATER = { ...FULL, moment: SIGNED, previous_seq: 7, next_seq: null };
    const list = () => focused('nldd-list');

    it('waits a frame: a new container has no box to focus before that', async () => {
      const nextFrame = heldFrames();
      const { container } = renderTab('/opdrachten/a1/geschiedenis', { stand: FULL });
      await waitFor(() => expect(container.querySelector('nldd-list-item')).not.toBeNull());
      act(() => navigateTo('/opdrachten/a1/geschiedenis?moment=7'));
      const title = () => container.querySelector(`nldd-title[text="${HEADING}"]`);
      await waitFor(() => expect(title()).not.toBeNull());
      expect(document.activeElement).toBe(document.body);
      nextFrame();
      expect(focused('nldd-title')).toBe(title());
      // Not a tab stop, and no ring around the whole width of the page.
      expect(document.activeElement).toHaveAttribute('tabindex', '-1');
      expect(document.activeElement).toHaveStyle({ outline: 'none' });
    });

    it('still lands when StrictMode runs the effect twice on a stand it already has', async () => {
      const { container } = renderTab('/opdrachten/a1/geschiedenis', {
        stand: FULL,
        strict: true,
      });
      await waitFor(() => expect(container.querySelector('nldd-list-item')).not.toBeNull());
      const title = () => container.querySelector(`nldd-title[text="${HEADING}"]`);
      act(() => navigateTo('/opdrachten/a1/geschiedenis?moment=7'));
      await waitFor(() => expect(focused('nldd-title')).not.toBeNull());
      expect(focused('nldd-title')).toBe(title());
      act(() => navigateTo('/opdrachten/a1/geschiedenis'));
      await waitFor(() => expect(list()).not.toBeNull());
      // From the cache: the stand is there as the part mounts.
      act(() => navigateTo('/opdrachten/a1/geschiedenis?moment=7'));
      await waitFor(() => expect(focused('nldd-title')).not.toBeNull());
      expect(focused('nldd-title')).toBe(title());
    });

    it('goes to the list on the way back to now', async () => {
      const { container } = renderTab('/opdrachten/a1/geschiedenis?moment=7', {
        stand: FULL,
        laterStand: LATER,
      });
      await waitFor(() =>
        expect(container.querySelector(`nldd-title[text="${HEADING}"]`)).not.toBeNull(),
      );
      act(() => navigateTo('/opdrachten/a1/geschiedenis'));
      await waitFor(() => expect(list()).toBe(container.querySelector('nldd-list')));
    });

    it('stays where the page starts on an address without a moment', async () => {
      const nextFrame = heldFrames();
      const { container } = renderTab('/opdrachten/a1/geschiedenis');
      await waitFor(() => expect(container.querySelector('nldd-list-item')).not.toBeNull());
      nextFrame();
      expect(document.activeElement).toBe(document.body);
    });
  });

  it('has no link where there is no moment to go to', async () => {
    const { container } = await opened({ ...FULL, next_seq: null, previous_seq: null });
    expect(container.querySelector('nldd-link[text="Vorige"]')).toBeNull();
    expect(container.querySelector('nldd-link[text="Volgende"]')).toBeNull();
    expect(container.querySelector('nldd-link[text="Terug naar nu"]')).not.toBeNull();
  });

  it('names what became known later, and what changed from outside the case', async () => {
    const { container } = await opened(FULL);
    expect(allText(container)).toContain('Tarief van categorie A op Tarieven 2027 gewijzigd.');
    // The values replace the wording without them.
    expect(allText(container)).not.toContain('De tarieven zijn gewijzigd.');
    const later = container.querySelector(
      `nldd-link[text="Later vastgelegd: ${SIGNED.statement}"]`,
    );
    expect(later).toHaveAttribute('href', '/opdrachten/a1/geschiedenis?moment=9');
  });

  it('shows a reader of class A the title, and no sentence, budget or amount', async () => {
    const { statement: _hidden, ...made } = MADE;
    const { container } = await opened(CLASS_A, [made, CLASS_A.moment]);
    const text = allText(container);
    expect(container.textContent).toContain('Begrotingsregel gewijzigd');
    expect(text).not.toContain(CHANGED.statement);
    expect(text).not.toContain('€');
    expect(text).not.toContain('Totaal begroot');
    expect(text).not.toContain('Offertebedrag');
    expect(text).not.toContain('Echtheidskenmerk');
    expect(text).not.toContain('Bekijk pdf');
    expect(text).not.toContain('Begroot');
    expect(text).not.toContain('Afgesproken bedrag');
    expect(text).not.toContain('Tarief van categorie');
    expect(text).toContain('De tarieven zijn gewijzigd.');
    expect(text).toContain('Voorbeeldministerie');
    // Nothing empty stands in for what is absent.
    expect(text).not.toContain('Nog niet ingevuld');
    expect(
      container.querySelector('nldd-list[accessible-label^="Gegevens van Offerte"]'),
    ).toBeNull();
    // What may be known still stands: the quote and its status, the course, the title of what came later.
    expect(container.querySelector('nldd-badge[text="Offerte gemaakt"]')).not.toBeNull();
    expect(text).toContain('De eigenaar is aan zet: de offerte.');
    expect(text).toContain('Later vastgelegd: Offerte getekend');
  });

  it('shows how the case had ended as a mark, with no course to walk', async () => {
    const { container } = await opened({
      ...FULL,
      course: { ...COURSE, next: null, ended: 'Niet doorgegaan' },
    });
    expect(container.querySelector('nldd-badge[text="Niet doorgegaan"]')).not.toBeNull();
    expect(container.querySelector('nldd-step-bar')).toBeNull();
  });

  it('says so when values were erased', async () => {
    const { container } = await opened({
      ...FULL,
      incomplete: true,
      course: null,
      assignment: { ...ASSIGNMENT, status: '', status_label: 'Onbekend' },
      budget: {
        lines: [{ ...FULL.budget!.lines[0]!, budgeted_cents: null }],
        removed: [],
        subtotals_by_year: {},
        total_budgeted_cents: null,
        previous_total_cents: null,
        pricing_error: null,
      },
    });
    const text = allText(container);
    expect(text).toContain('Een deel van de waarden is gewist.');
    // Half a story states no status and no total.
    expect(text).not.toContain('Onbekend');
    expect(text).not.toContain('Totaal begroot');
    expect(text).toContain('Niet berekend');
  });

  it('draws how the assignment stood, not how it stands', async () => {
    const { container } = await opened({
      ...FULL,
      assignment: {
        ...ASSIGNMENT,
        client_name: 'Eerdere opdrachtgever',
        start_date: '2025-02-01',
        end_date: '2025-03-31',
        notes: 'Notitie van toen',
        verbal_agreement_note: 'Mondeling van "toen" ',
        quoted_amount_cents: 13000000,
      },
    });
    const text = allText(container);
    expect(text).toContain('Eerdere opdrachtgever');
    expect(text).toContain('1 feb 2025 t/m 31 mrt 2025');
    expect(text).toContain('Notitie van toen');
    expect(text).toContain('Mondeling akkoord');
    expect(text).toContain('Afgesproken bedrag');
    expect(text).toContain('€ 130.000');
  });

  it('leaves out what there was not, and what stands elsewhere on the screen', async () => {
    // The first quote sets the agreed amount: the quote says it already.
    const told = await opened({
      ...FULL,
      assignment: { ...ASSIGNMENT, client_name: null, quoted_amount_cents: 12000000 },
    });
    expect(allText(told.container)).not.toContain('Afgesproken bedrag');
    expect(allText(told.container)).not.toContain('Opdrachtgever');
    expect(allText(told.container)).not.toContain('Notities');
    told.unmount();
    // At its own moment the note is the reason under the sentence.
    const note = 'Telefonisch akkoord gegeven';
    const agreed = await opened({
      ...FULL,
      moment: { ...CHANGED, lines: [note] },
      assignment: { ...ASSIGNMENT, verbal_agreement_note: note },
    });
    expect(allText(agreed.container)).toContain(note);
    expect(allText(agreed.container)).not.toContain('Mondeling akkoord');
  });

  it('reads well when the notes stand only on their row', async () => {
    const { container } = await opened(FULL);
    const count = (word: string) => allText(container).split(word).length - 1;
    expect(count('Akkoord met de uren')).toBe(1);
    expect(count('Te duur')).toBe(1);
    expect(container.textContent).toContain(CHANGED.statement);
  });

  it('draws what was written with a fact under its sentence', async () => {
    const { container } = await opened({
      ...FULL,
      moment: {
        ...CHANGED,
        fact: 'acceptance_date_corrected',
        title: 'Datum van tekenen gecorrigeerd',
        statement:
          'Anna Voorbeeld corrigeerde de datum van tekenen van 3 maart 2026 naar 6 maart 2026.',
        lines: ['Verkeerd overgenomen'],
      },
    });
    expect(allText(container)).toContain('Verkeerd overgenomen');
  });

  it('says of a quote what its card said then', async () => {
    const open: StandQuote = {
      ...QUOTE_VALUES,
      id: 'q1',
      reference: 'VG-2026-0007',
      status: 'issued',
      status_label: 'Offerte gemaakt',
      changed: true,
    };
    const { container } = await opened({
      ...FULL,
      quotes: [{ ...open, approvals: [APPROVAL_ROW] }],
    });
    expect(container.querySelector('nldd-badge[text="Wacht op goedkeuring"]')).not.toBeNull();
    expect(container.querySelector('nldd-badge[text="Offerte gemaakt"]')).toBeNull();
  });

  it('uses none of the words of the system', async () => {
    const { container } = await opened(FULL);
    const text = allText(container).toLowerCase();
    for (const word of ['chronolexogram', 'kroniek', 'reductie', 'lexostatus', 'decretogram']) {
      expect(text).not.toContain(word);
    }
  });

  it('says a moment was not found, and offers the way back', async () => {
    const { container } = renderTab('/opdrachten/a1/geschiedenis?moment=99');
    await waitFor(() =>
      expect(container.querySelector('nldd-link[text="Terug naar nu"]')).not.toBeNull(),
    );
    expect(allText(container)).toContain('Dit moment');
  });
});

describe('the words of a moment', () => {
  it('writes the moment on the clock of the instance', () => {
    expect(standTitle('2026-11-03T13:02:00Z')).toBe(HEADING);
    expect(standTitle('2026-07-31T22:30:00Z')).toBe('Stand op 1 augustus 2026, 00:30');
  });

  it('says who established a moment, also where no name says so', () => {
    const by = (actor_kind: Moment['actor_kind'], actor_name: string | null = null) =>
      plain(momentByline({ ...MADE, actor_kind, actor_name }))
        .split(' · ')
        .slice(1);
    expect(by('person', 'Anna Voorbeeld')).toEqual(['Anna Voorbeeld']);
    expect(by('peer')).toEqual(['Andere instantie']);
    expect(by('guest')).toEqual(['Gast']);
    expect(by('system')).toEqual(['Systeem']);
    expect(by('person')).toEqual(['Onbekend']);
    // A name goes before the kind, and without either nothing stands in for it.
    expect(by('guest', 'Bert Voorbeeld')).toEqual(['Bert Voorbeeld']);
    expect(by(null)).toEqual([]);
  });

  describe('an approval', () => {
    const approved: StandApproval = {
      ...APPROVAL_ROW,
      status: 'approved',
      decided_by_name: 'Carla Voorbeeld',
      decided_at: '2026-11-04T10:00:00Z',
    };

    it('says who took back an approval and when, not who gave it', () => {
      const { text } = approvalTold({
        ...approved,
        status: 'withdrawn',
        withdrawn_by_name: 'Noor Voorbeeld',
        withdrawn_at: '2026-11-06T10:00:00Z',
      });
      expect(text).toMatch(/^Goedkeuring ingetrokken op 6 nov 2026.* door Noor Voorbeeld$/);
      expect(text).not.toContain('4 nov');
      expect(text).not.toContain('Carla');
    });

    it('calls taking back an open request what it is', () => {
      expect(
        approvalTold({
          ...APPROVAL_ROW,
          status: 'withdrawn',
          withdrawn_by_name: 'Anna Voorbeeld',
          withdrawn_at: '2026-11-06T10:00:00Z',
        }).text,
      ).toMatch(/^Aanvraag ingetrokken op 6 nov 2026.* door Anna Voorbeeld$/);
      // A row without the fields says only what happened.
      expect(approvalTold({ ...APPROVAL_ROW, status: 'withdrawn' }).text).toBe(
        'Aanvraag ingetrokken',
      );
    });

    it('says of a self-approval whether the approver asked or made it', () => {
      const self = { ...approved, self_approved: true };
      expect(approvalTold(self).text).toMatch(/, die de offerte ook maakte$/);
      expect(approvalTold({ ...self, requested_by_name: 'Carla Voorbeeld' }).text).toMatch(
        /, die de goedkeuring zelf vroeg$/,
      );
      expect(
        approvalTold({ ...self, decided_by_name: null, requested_by_name: null }).text,
      ).toMatch(/, die de offerte ook maakte$/);
    });
  });

  describe('a signing link', () => {
    const offer = {
      channel: 'signing_link',
      recipient: 'tekenaar@voorbeeld.example',
      offered_at: '2026-11-03T10:00:00Z',
      offered_by_name: 'Anna Voorbeeld',
    };
    const invitation = {
      state: 'invited',
      expires_at: '2026-12-03T10:00:00Z',
      opened_at: null,
      used_at: null,
      withdrawn_at: null,
    };

    it('says a withdrawn or expired link with the words of the card', () => {
      expect(
        offerTold({
          ...offer,
          invitation: { ...invitation, state: 'withdrawn', withdrawn_at: '2026-11-04T10:00:00Z' },
        }).note,
      ).toMatch(/^Op 3 nov 2026.* door Anna Voorbeeld · Tekenlink ingetrokken op 4 nov 2026/);
      expect(offerTold({ ...offer, invitation: { ...invitation, state: 'expired' } }).note).toMatch(
        /^Op 3 nov 2026.* · Tekenlink verlopen op 3 dec 2026$/,
      );
    });

    it('says only when and by whom it was offered without an ended link in the answer', () => {
      for (const told of [
        offerTold({ ...offer, invitation }),
        offerTold({ ...offer, invitation: null }),
        offerTold(offer),
      ]) {
        expect(told.note).toMatch(/^Op 3 nov 2026.* door Anna Voorbeeld$/);
      }
    });

    it('leaves the word to the label of the row, also without a name', () => {
      for (const told of [
        offerTold(offer),
        offerTold({ ...offer, offered_by_name: null }),
        offerTold({ ...offer, invitation: { ...invitation, state: 'expired' } }),
      ]) {
        expect(told.note).not.toMatch(/aangeboden/i);
      }
    });
  });

  describe('a signature', () => {
    const signed: StandAcceptance = {
      signer_name: 'Tekenaar Voorbeeld',
      form: 'signing_link',
      signed_at: '2026-10-31T12:00:00Z',
      organisation_name: 'Voorbeeldministerie',
      recorded_by_name: 'Tekenaar Voorbeeld',
    };

    it('does not name the signer a second time', () => {
      expect(acceptanceTold(signed)).toEqual({
        text: 'Getekend op 31 okt 2026 door Tekenaar Voorbeeld namens Voorbeeldministerie',
        note: 'Getekend via de tekenlink',
      });
    });

    it('names who recorded it when that was someone else, or no one', () => {
      expect(
        acceptanceTold({ ...signed, form: 'uploaded_pdf', recorded_by_name: 'Anna Voorbeeld' })
          .note,
      ).toBe('Getekende pdf vastgelegd door Anna Voorbeeld');
      expect(acceptanceTold({ ...signed, recorded_by_name: null }).note).toBe(
        'Getekend via de tekenlink',
      );
    });
  });

  describe('a budget line', () => {
    const line: StandBudgetLine = {
      id: 'l1',
      description: 'Standards engineer: coördinatie "#2" & co',
      kind: 'personnel',
      position: 1,
      role: 'Standards engineer',
      fte: '0.6',
      change: null,
    };

    it('leaves out the role where the name starts with it', () => {
      expect(budgetLineSummary(line)).toBe('0,6 FTE');
      expect(budgetLineSummary({ ...line, description: 'Standards engineer' })).toBe('0,6 FTE');
      // The server takes a description that holds the role as it is, capitals included.
      expect(
        budgetLineSummary({ ...line, description: 'standards engineer voor coördinatie' }),
      ).toBe('0,6 FTE');
    });

    it('keeps the role where the name does not start with it', () => {
      expect(budgetLineSummary({ ...line, description: 'Senior standards engineer' })).toBe(
        'Standards engineer · 0,6 FTE',
      );
    });

    it('says nothing of a role that is not there', () => {
      const { role: _absent, ...noRole } = line;
      expect(budgetLineSummary(noRole)).toBe('0,6 FTE');
      expect(budgetLineSummary({ ...line, role: null })).toBe('0,6 FTE');
      expect(budgetLineSummary({ ...line, role: '' })).toBe('0,6 FTE');
    });
  });

  it('words a quote as its card does, from what the reader has', () => {
    const quote = {
      id: 'q1',
      reference: null,
      status: 'issued',
      status_label: 'Offerte gemaakt',
      changed: false,
    };
    const row = (status: string) => ({ ...APPROVAL_ROW, status });
    const offer = {
      channel: 'document',
      recipient: null,
      offered_at: '2026-11-03T10:00:00Z',
      offered_by_name: null,
    };
    // A reader without offers and approvals gets the plain word.
    expect(standQuoteLabel(quote)).toBe('Offerte gemaakt');
    expect(standQuoteLabel({ ...quote, approvals: [], offers: [] })).toBe('Offerte gemaakt');
    expect(standQuoteLabel({ ...quote, approvals: [row('requested')] })).toBe(
      'Wacht op goedkeuring',
    );
    expect(standQuoteLabel({ ...quote, approvals: [row('sent_back')] })).toBe('Teruggestuurd');
    expect(standQuoteLabel({ ...quote, approvals: [row('approved')] })).toBe('Offerte gemaakt');
    expect(standQuoteLabel({ ...quote, approvals: [row('withdrawn'), row('requested')] })).toBe(
      'Wacht op goedkeuring',
    );
    // Asked again and taken back: the card says the status, not the earlier refusal.
    expect(standQuoteLabel({ ...quote, approvals: [row('sent_back'), row('withdrawn')] })).toBe(
      'Offerte gemaakt',
    );
    // An offer goes before the approval, and a decision before both.
    expect(standQuoteLabel({ ...quote, approvals: [row('approved')], offers: [offer] })).toBe(
      'Aangeboden',
    );
    expect(standQuoteLabel({ ...quote, status: 'accepted', offers: [offer] })).toBe('Akkoord');
    expect(standQuoteLabel({ ...quote, status: 'rejected', offers: [offer] })).toBe('Afgewezen');
  });

  it('says what came later in the words the reader may read', () => {
    expect(laterKnownText({ seq: 9, title: 'x', statement: 'Bert tekende.' })).toBe(
      'Later vastgelegd: Bert tekende.',
    );
    expect(laterKnownText({ seq: 9, title: 'Offerte getekend' })).toBe(
      'Later vastgelegd: Offerte getekend',
    );
  });
});

describe('the address and the cache', () => {
  it('reads only a whole number as a moment', () => {
    expect(momentOf(new URLSearchParams('moment=12'))).toBe(12);
    expect(momentOf(new URLSearchParams('moment=abc'))).toBeNull();
    expect(momentOf(new URLSearchParams('moment='))).toBeNull();
    expect(momentOf(new URLSearchParams(''))).toBeNull();
  });

  it('keeps away from the key every save invalidates', () => {
    expect(chronicleKeys.moments('a1')).toEqual(['chronicle', 'a1']);
    expect(chronicleKeys.stand('a1', 7)).toEqual(['chronicle', 'a1', 7]);
  });
});

describe('taking a text out of a moment', () => {
  const NOTES = {
    key: 'assignment.notes',
    label: 'Notities',
    text: 'Bel de heer Voorbeeld terug.',
    kept: ['De tekst staat ook in offerte VG-2026-0007; die blijft zoals ze is gemaakt.'],
  };
  const NAME = { key: 'assignment.name', label: 'Naam', kept: [] };

  const opened = async (stand: Stand, extra: Record<string, unknown> = {}) => {
    const view = renderTab('/opdrachten/a1/geschiedenis?moment=7', { stand, extra });
    await waitFor(() =>
      expect(view.container.querySelector(`nldd-title[text="${HEADING}"]`)).not.toBeNull(),
    );
    return view;
  };

  const menuItem = (root: ParentNode) =>
    root.querySelector('nldd-menu-item[text="Verwijder een tekst"]');

  const posts = (fetchMock: ReturnType<typeof stubApi>) =>
    (fetchMock.mock.calls as [RequestInfo | URL, RequestInit?][]).filter(
      ([, init]) => init?.method === 'POST',
    );

  const openSheet = async (view: Awaited<ReturnType<typeof opened>>) => {
    await waitFor(() => expect(menuItem(view.container)).not.toBeNull());
    act(() => {
      menuItem(view.container)?.dispatchEvent(new CustomEvent('select'));
    });
    await waitFor(() => expect(document.querySelector('nldd-sheet[open]')).not.toBeNull());
    return document.querySelector('nldd-sheet[open]') as Element;
  };

  it('offers the menu item only for a moment with texts that may be taken out', async () => {
    const withTexts = await opened({ ...FULL, removable_texts: [NOTES] });
    await waitFor(() => expect(menuItem(withTexts.container)).not.toBeNull());
    expect(
      withTexts.container.querySelector('nldd-menu-item[text="Verwijder een tekst"]'),
    ).not.toBeNull();
    withTexts.unmount();
    for (const removable of [undefined, null, []] as Stand['removable_texts'][]) {
      const { container, unmount } = await opened({ ...FULL, removable_texts: removable });
      expect(menuItem(container)).toBeNull();
      unmount();
    }
  });

  it('shows each text with its label and what stays, and asks to choose before sending', async () => {
    const view = await opened({ ...FULL, removable_texts: [NOTES, NAME] });
    const sheet = await openSheet(view);
    expect(sheet.querySelector('nldd-title')?.getAttribute('text')).toBe(
      'Tekst verwijderen uit dit moment',
    );
    const fields = [...sheet.querySelectorAll('nldd-form-field')];
    expect(fields.map((field) => field.getAttribute('label'))).toEqual(['Notities', 'Naam']);
    expect(fields[0]?.getAttribute('supporting-label')).toBe(NOTES.kept[0]);
    expect(fields[1]?.hasAttribute('supporting-label')).toBe(false);
    expect(
      [...sheet.querySelectorAll('nldd-checkbox-field')].map((box) => box.getAttribute('label')),
    ).toEqual(['Bel de heer Voorbeeld terug.', 'Naam']);
    expect(sheet.querySelectorAll('nldd-checkbox-field[checked]')).toHaveLength(0);
    sheet.querySelector('nldd-form')?.dispatchEvent(new Event('submit', { cancelable: true }));
    await waitFor(() =>
      expect(sheet.querySelector('nldd-banner[variant="critical"]')?.getAttribute('text')).toBe(
        'Kies de tekst die je wilt verwijderen.',
      ),
    );
    expect(posts(view.fetchMock)).toEqual([]);
  });

  it('sends the chosen keys and closes the sheet', async () => {
    const view = await opened(
      { ...FULL, removable_texts: [NOTES, NAME] },
      {
        'POST /api/assignments/a1/chronicle/7/restate': {
          stand: { ...FULL, removable_texts: [NAME] },
          kept: [],
        },
      },
    );
    const sheet = await openSheet(view);
    act(() => {
      sheet
        .querySelector('nldd-checkbox-field')
        ?.dispatchEvent(new CustomEvent('change', { detail: { checked: true } }));
    });
    await waitFor(() =>
      expect(sheet.querySelector('nldd-checkbox-field')?.hasAttribute('checked')).toBe(true),
    );
    fireEvent.submit(sheet.querySelector('nldd-form')!);
    await waitFor(() => expect(posts(view.fetchMock)).toHaveLength(1));
    const [url, init] = posts(view.fetchMock)[0]!;
    expect(String(url)).toBe('/api/assignments/a1/chronicle/7/restate');
    expect(JSON.parse(String(init?.body))).toEqual({ columns: ['assignment.notes'] });
    await waitFor(() => expect(document.querySelector('nldd-sheet[open]')).toBeNull());
  });

  it('keeps the sheet open and says why when the server refuses', async () => {
    const view = await opened({ ...FULL, removable_texts: [NOTES] });
    const sheet = await openSheet(view);
    act(() => {
      sheet
        .querySelector('nldd-checkbox-field')
        ?.dispatchEvent(new CustomEvent('change', { detail: { checked: true } }));
    });
    fireEvent.submit(sheet.querySelector('nldd-form')!);
    await waitFor(() => expect(posts(view.fetchMock)).toHaveLength(1));
    await waitFor(() =>
      expect(sheet.querySelector('nldd-banner[variant="critical"]')).not.toBeNull(),
    );
    expect(document.querySelector('nldd-sheet[open]')).not.toBeNull();
  });

  it('links to the moment that took a text out', async () => {
    const { container } = await opened({
      ...FULL,
      restated: [{ seq: 12, occurred_at: '2026-11-20T09:00:00Z', removed: ['Notities'] }],
    });
    const link = container.querySelector('nldd-link[text="Later verwijderd: notities"]');
    expect(link).toHaveAttribute('href', '/opdrachten/a1/geschiedenis?moment=12');
  });

  it('says in words what was taken out', () => {
    const at = (removed: string[]) =>
      restatedText({ seq: 12, occurred_at: '2026-11-20T09:00:00Z', removed });
    expect(at(['Notities'])).toBe('Later verwijderd: notities');
    expect(at(['Naam', 'Notities'])).toBe('Later verwijderd: naam en notities');
    expect(at(['Naam', 'Notities', 'Omschrijving'])).toBe(
      'Later verwijderd: naam, notities en omschrijving',
    );
  });
});
