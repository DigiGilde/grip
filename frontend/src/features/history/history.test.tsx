import { waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { mockApi } from '@/features/assignments/testing';
import { renderApp } from '@/test/utils';
import type { HistoryEvent } from './api';
import { NewUpdates } from './NewUpdates';
import { UpdateFeed } from './UpdateFeed';
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

describe('NewUpdates', () => {
  afterEach(() => vi.unstubAllGlobals());

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

  function show(items: UpdateItem[]) {
    const fetchMock = mockApi({
      '/api/updates': { items, new_count: 0, next: null },
      '/api/updates/seen': {},
    });
    return { ...renderApp(<NewUpdates limit={3} />), fetchMock };
  }

  it('asks for three, shows a row each to what it is about, and the way to all', async () => {
    const { container, fetchMock } = show([
      item('u1'),
      item('u2', { parts: [{ text: 'Zonder adres' }] }),
    ]);
    await waitFor(() => expect(container.querySelector('nldd-list')).not.toBeNull());
    expect((fetchMock.mock.calls as unknown[][]).map((call) => String(call[0]))).toContain(
      '/api/updates?limiet=3',
    );
    const rows = [...container.querySelectorAll('nldd-list-item')];
    expect(rows.map((row) => row.getAttribute('href'))).toEqual([
      '/opdrachten/a1',
      null,
      '/wat-is-er-gebeurd',
    ]);
    expect(rows[2]!.querySelector('nldd-text-cell')?.getAttribute('text')).toBe(
      'Alles wat er gebeurd is',
    );
  });

  it('marks what is new', async () => {
    const { container } = show([item('u1', { new: true })]);
    await waitFor(() => expect(container.querySelector('nldd-list')).not.toBeNull());
    expect(container.querySelector('nldd-text-cell')?.getAttribute('supporting-text')).toBe(
      'nieuw · vanochtend',
    );
  });

  it('is not there when nothing happened', async () => {
    const { container, fetchMock } = show([]);
    await waitFor(() => expect(requested(fetchMock)).toContain('/api/updates?limiet=3'));
    expect(container.querySelector('nldd-title')).toBeNull();
    expect(container.querySelector('nldd-list')).toBeNull();
  });

  it('does not mark the feed as seen: three rows are not all of it', async () => {
    const { container, fetchMock } = show([item('u1', { new: true })]);
    await waitFor(() => expect(container.querySelector('nldd-list')).not.toBeNull());
    expect(requested(fetchMock)).not.toContain('/api/updates/seen');
  });
});

describe('UpdateFeed', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('marks the feed as seen once it is shown', async () => {
    const fetchMock = mockApi({
      '/api/updates': {
        items: [
          {
            id: 'u1',
            seq: 1,
            kind: 'x',
            when: '2026-11-04T08:00:00Z',
            when_text: 'vanochtend',
            day: 'Vandaag',
            parts: [{ text: 'Iets gebeurde' }],
            text: 'Iets gebeurde',
            count: 1,
            new: true,
          },
        ],
        new_count: 1,
        next: null,
      },
      '/api/updates/seen': {},
    });
    renderApp(<UpdateFeed limit={20} paged level={2} />);
    await waitFor(() => expect(requested(fetchMock)).toContain('/api/updates/seen'));
  });
});
