import { waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { mockApi } from '@/features/assignments/testing';
import { renderApp } from '@/test/utils';
import type { HistoryEvent } from './api';
import { NewUpdates } from './NewUpdates';
import { UpdateFeed, UpdatesPage } from './UpdateFeed';
import type { UpdateItem } from './updates';
import { actor, detail, headline, moments } from './words';

function event(overrides: Partial<HistoryEvent>): HistoryEvent {
  return {
    seq: 1,
    id: 'e-1',
    occurred_at: '2026-07-01T09:30:00+00:00',
    type: 'budget_line.updated',
    subject_kind: 'budget_line',
    actor_kind: 'person',
    actor_name: 'Bea Beheer',
    correlation_id: 'c-1',
    changes: [],
    details_visible: true,
    ...overrides,
  };
}

const scale = (visible: boolean) =>
  event({
    type: 'person_scale.updated',
    subject_kind: 'person_scale',
    person_name: 'Lot Lid',
    changes: visible
      ? [
          { field: 'billing_scale', visible: true, old: 11, new: 12 },
          { field: 'valid_from', visible: true, old: null, new: '2026-07-01' },
        ]
      : [
          { field: 'billing_scale', visible: false },
          { field: 'valid_from', visible: false },
        ],
    details_visible: visible,
  });

describe('an event in words', () => {
  it('says from what to what to a reader who may see the values', () => {
    expect(headline(scale(true))).toBe('Schaal van Lot Lid gewijzigd');
    expect(detail(scale(true))).toBe('Schaal van 11 naar 12 per 1 jul 2026');
  });

  it('says only that it changed to a reader who may not', () => {
    expect(headline(scale(false))).toBe('Schaal van Lot Lid gewijzigd');
    expect(detail(scale(false))).toBe('');
  });

  it('leaves the person out when the reader may not know who', () => {
    expect(headline({ ...scale(false), person_name: null })).toBe('Schaal gewijzigd');
  });

  it('writes amounts and dates as the rest of grip does', () => {
    const line = event({
      changes: [
        { field: 'amount_cents', visible: true, old: 1000000, new: 1250000 },
        { field: 'end_date', visible: true, old: '2026-09-30', new: '2026-12-31' },
        { field: 'position', visible: true, old: 1, new: 2 },
      ],
    });
    expect(headline(line)).toBe('Begrotingsregel gewijzigd');
    // A field without a Dutch name is not shown under its code name.
    // The euro sign is followed by a no-break space.
    expect(detail(line).replace(/\u00a0/g, ' ')).toBe(
      'Bedrag van € 10.000 naar € 12.500 · Einddatum van 30 sep 2026 naar 31 dec 2026',
    );
  });

  it('has a sentence for what is more than a change of fields', () => {
    expect(headline(event({ type: 'quote.accepted', subject_kind: 'quote' }))).toBe(
      'Offerte getekend',
    );
    expect(
      detail(
        event({
          type: 'assignment.status_changed',
          subject_kind: 'assignment',
          payload: { new_status: 'active', reason: 'mondeling akkoord' },
        }),
      ),
    ).toBe('Status active · Reden mondeling akkoord');
  });

  it('names who did it, also when that is no person', () => {
    expect(actor(event({}))).toBe('Bea Beheer');
    expect(actor(event({ actor_kind: 'system', actor_name: null }))).toBe('Systeem');
    expect(actor(event({ actor_kind: 'guest', actor_name: null }))).toBe('Gast');
    expect(actor(event({ actor_kind: 'peer', actor_name: null }))).toBe('Andere instantie');
  });

  it('takes the sentence and the lines of the server over its own', () => {
    const made = event({
      type: 'assignment.created',
      subject_kind: 'assignment',
      title: 'Opdracht toegevoegd',
      lines: ['Naam Opdracht Voorbeeld', 'Status In voorbereiding'],
      changes: [{ field: 'status', visible: true, old: null, new: 'draft' }],
    });
    expect(headline(made)).toBe('Opdracht toegevoegd');
    // Never the code value the stream holds.
    expect(detail(made)).toBe('Naam Opdracht Voorbeeld · Status In voorbereiding');
    expect(detail(made)).not.toContain('draft');
  });

  it('says that values were erased', () => {
    expect(detail(event({ erased: true }))).toBe('De waarden zijn gewist');
  });
});

describe('moments', () => {
  it('shows what one action changed as one row, named after what it was about', () => {
    const rows = moments([
      event({ seq: 3, type: 'quote.accepted', subject_kind: 'quote', correlation_id: 'c-2' }),
      event({
        seq: 2,
        type: 'assignment.updated',
        subject_kind: 'assignment',
        correlation_id: 'c-2',
        changes: [{ field: 'status', visible: true, old: 'offered', new: 'active' }],
      }),
      event({ seq: 1, correlation_id: 'c-1' }),
    ]);
    expect(rows.map((row) => row.headline)).toEqual([
      'Offerte getekend',
      'Begrotingsregel gewijzigd',
    ]);
    expect(rows[0]?.lines).toEqual(['Opdracht gewijzigd: Status van offered naar active']);
    expect(rows[1]?.lines).toEqual([]);
  });

  it('does not repeat the same line', () => {
    const rows = moments([
      event({ seq: 2, correlation_id: 'c-3' }),
      event({ seq: 1, correlation_id: 'c-3' }),
    ]);
    expect(rows).toHaveLength(1);
    expect(rows[0]?.lines).toEqual([]);
  });
});

const requested = (fetchMock: { mock: { calls: unknown[][] } }) =>
  fetchMock.mock.calls.map((call) => String(call[0]));

const item = (id: string, over: Partial<UpdateItem> = {}): UpdateItem => ({
  id,
  seq: 1,
  kind: 'x',
  when: '2026-11-04T08:00:00Z',
  when_text: 'vanochtend',
  day: 'Vandaag',
  parts: [{ text: 'Opdracht Alfa', href: '/opdrachten/a1' }, { text: ' is gestart' }],
  text: 'Opdracht Alfa is gestart',
  count: 1,
  new: false,
  ...over,
});

const page = (items: UpdateItem[]) => ({ items, new_count: 0, next: null });

const headings = (container: HTMLElement) =>
  [...container.querySelectorAll('nldd-title[text]')].map((title) => [
    title.getAttribute('text'),
    title.getAttribute('heading-level'),
  ]);

const dayList = (container: HTMLElement, day: string) =>
  container.querySelector(`nldd-list[accessible-label="Wat er gebeurde: ${day}"]`);

const places = (list: Element | null) =>
  [...(list?.querySelectorAll('nldd-step-cell') ?? [])].map((cell) =>
    cell.getAttribute('position'),
  );

describe('NewUpdates', () => {
  afterEach(() => vi.unstubAllGlobals());

  function show(items: UpdateItem[]) {
    const fetchMock = mockApi({
      '/api/updates': page(items),
      '/api/updates/seen': {},
    });
    return { ...renderApp(<NewUpdates limit={5} />), fetchMock };
  }

  it('asks for five and puts them on the track of their day, under a heading at level 3', async () => {
    const { container, fetchMock } = show([
      item('u3'),
      item('u2', { parts: [{ text: 'Zonder adres' }], text: 'Zonder adres' }),
      item('u1', { day: 'Gisteren', when_text: 'gisteren' }),
    ]);
    await waitFor(() => expect(container.querySelector('nldd-list')).not.toBeNull());
    expect(requested(fetchMock)).toContain('/api/updates?limiet=5');
    expect(headings(container)).toEqual([
      ['Nieuw', '2'],
      ['Vandaag', '3'],
      ['Gisteren', '3'],
    ]);
    // The track joins the items of one day; an item alone has none.
    expect(places(dayList(container, 'Vandaag'))).toEqual(['first', 'last']);
    expect(places(dayList(container, 'Gisteren'))).toEqual(['only']);
    for (const cell of container.querySelectorAll('nldd-step-cell')) {
      expect([cell.getAttribute('status'), cell.getAttribute('level')]).toEqual(['past', 'minor']);
    }
  });

  it('keeps the sentence with its link and the time, and ends with the way to all', async () => {
    const { container } = show([
      item('u2'),
      item('u1', { parts: [{ text: 'Zonder adres' }], text: 'Zonder adres' }),
    ]);
    await waitFor(() => expect(container.querySelector('nldd-list')).not.toBeNull());
    const today = dayList(container, 'Vandaag')!;
    const rows = [...today.querySelectorAll('nldd-list-item')];
    // The thing a sentence is about is the link; the row itself leads nowhere.
    expect(rows.map((row) => row.getAttribute('href'))).toEqual([null, null]);
    const links = [...today.querySelectorAll('nldd-link')];
    expect(links.map((link) => [link.getAttribute('href'), link.getAttribute('text')])).toEqual([
      ['/opdrachten/a1', 'Opdracht Alfa'],
    ]);
    expect(rows[0]!.textContent).toBe(' is gestartvanochtend');
    expect(rows[1]!.textContent).toBe('Zonder adresvanochtend');
    const all = container.querySelector('nldd-list-item[href="/wat-is-er-gebeurd"]');
    expect(all?.querySelector('nldd-text-cell')?.getAttribute('text')).toBe(
      'Alles wat er gebeurd is',
    );
  });

  it('marks what is new, in its sentence and in its time', async () => {
    const { container } = show([item('u1', { new: true })]);
    await waitFor(() => expect(container.querySelector('nldd-list')).not.toBeNull());
    expect(
      container.querySelector('nldd-cell[width="full"] nldd-text')?.getAttribute('weight'),
    ).toBe('bold');
    expect(container.querySelector('nldd-cell[horizontal-alignment="right"]')?.textContent).toBe(
      'nieuw · vanochtend',
    );
  });

  it('is not there when nothing happened', async () => {
    const { container, fetchMock } = show([]);
    await waitFor(() => expect(requested(fetchMock)).toContain('/api/updates?limiet=5'));
    expect(container.querySelector('nldd-title')).toBeNull();
    expect(container.querySelector('nldd-list')).toBeNull();
  });

  it('does not mark the feed as seen: five rows are not all of it', async () => {
    const { container, fetchMock } = show([item('u1', { new: true })]);
    await waitFor(() => expect(container.querySelector('nldd-list')).not.toBeNull());
    expect(requested(fetchMock)).not.toContain('/api/updates/seen');
  });
});

describe('UpdateFeed', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('marks the feed as seen once it is shown', async () => {
    const fetchMock = mockApi({
      '/api/updates': page([item('u1', { parts: [{ text: 'Iets gebeurde' }], new: true })]),
      '/api/updates/seen': {},
    });
    renderApp(<UpdateFeed limit={20} paged level={2} />);
    await waitFor(() => expect(requested(fetchMock)).toContain('/api/updates/seen'));
  });

  it('does not mark it as seen when a filter narrows it: a part is not all of it', async () => {
    const fetchMock = mockApi({
      '/api/updates': page([item('u1', { new: true })]),
      '/api/updates/seen': {},
    });
    const { container } = renderApp(
      <UpdateFeed limit={20} paged level={2} filter={{ opdracht: 'a1' }} />,
    );
    await waitFor(() => expect(container.querySelector('nldd-list')).not.toBeNull());
    expect(requested(fetchMock)).toContain('/api/updates?limiet=20&opdracht=a1');
    expect(requested(fetchMock)).not.toContain('/api/updates/seen');
  });

  it('says nothing was found when a filter leaves nothing', async () => {
    mockApi({ '/api/updates': page([]), '/api/updates/seen': {} });
    const { container } = renderApp(
      <UpdateFeed limit={20} paged level={2} filter={{ persoon: 'p1' }} />,
    );
    await waitFor(() =>
      expect(
        container.querySelector('nldd-inline-dialog[data-state="empty"]')?.getAttribute('text'),
      ).toBe('Niets gevonden'),
    );
  });
});

describe('UpdatesPage', () => {
  afterEach(() => vi.unstubAllGlobals());

  const OPTIONS = {
    assignments: [
      { id: 'a1', name: 'Opdracht Alfa' },
      { id: 'a2', name: 'Opdracht Beta' },
    ],
    people: [{ id: 'p2', name: 'Pim Planner' }],
  };

  function showPage(path: string, items: UpdateItem[] = [item('u1')]) {
    const fetchMock = mockApi({
      '/api/updates/filters': OPTIONS,
      '/api/updates': page(items),
      '/api/updates/seen': {},
    });
    return { ...renderApp(<UpdatesPage />, { path }), fetchMock };
  }

  const select = (container: HTMLElement, label: string) =>
    container.querySelector<HTMLSelectElement>(`select[aria-label="${label}"]`);

  it('reads the filters from the address, asks the feed for them and shows them chosen', async () => {
    const { container, fetchMock } = showPage('/wat-is-er-gebeurd?opdracht=a1&persoon=p2');
    await waitFor(() => expect(select(container, 'Persoon')).not.toBeNull());
    expect(requested(fetchMock)).toContain('/api/updates?limiet=20&opdracht=a1&persoon=p2');
    expect(select(container, 'Opdracht')).toHaveValue('a1');
    expect(select(container, 'Persoon')).toHaveValue('p2');
    expect([...select(container, 'Opdracht')!.options].map((option) => option.text)).toEqual([
      'Alle opdrachten',
      'Opdracht Alfa',
      'Opdracht Beta',
    ]);
    expect([...select(container, 'Persoon')!.options].map((option) => option.text)).toEqual([
      'Iedereen',
      'Pim Planner',
    ]);
    await waitFor(() => expect(container.querySelector('nldd-list')).not.toBeNull());
    expect(requested(fetchMock)).not.toContain('/api/updates/seen');
  });

  it('draws the same timeline, with the days as headings at level 2', async () => {
    const { container } = showPage('/wat-is-er-gebeurd', [
      item('u2'),
      item('u1', { day: 'Gisteren', when_text: 'gisteren' }),
    ]);
    await waitFor(() => expect(container.querySelector('nldd-list')).not.toBeNull());
    expect(headings(container)).toEqual([
      ['Vandaag', '2'],
      ['Gisteren', '2'],
    ]);
    expect(places(dayList(container, 'Vandaag'))).toEqual(['only']);
  });

  it('lets go of an id the options do not hold, and reads the whole feed', async () => {
    const { container, fetchMock } = showPage('/wat-is-er-gebeurd?opdracht=a9&persoon=p2');
    await waitFor(() =>
      expect(requested(fetchMock)).toContain('/api/updates?limiet=20&persoon=p2'),
    );
    expect(select(container, 'Opdracht')).toHaveValue('');
    expect(select(container, 'Persoon')).toHaveValue('p2');
  });
});

