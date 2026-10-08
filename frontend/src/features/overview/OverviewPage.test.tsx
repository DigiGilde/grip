import { screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { renderApp } from '@/test/utils';
import { OverviewPage } from './OverviewPage';
import { currentYearChoice, yearOptions } from './years';

function respondWith(body: unknown, status = 200) {
  const fetchMock = vi.fn(() =>
    Promise.resolve(
      new Response(JSON.stringify(body), {
        status,
        headers: {
          'Content-Type': status === 200 ? 'application/json' : 'application/problem+json',
        },
      }),
    ),
  );
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

const TOTALS = {
  budgeted_cents: 18780000,
  realised_cents: 2700000,
  forecast_cents: 13500000,
  coverage_cents: 450000,
  used_cents: 16650000,
  available_cents: 2130000,
  overrun: false,
};

const ROW = {
  assignment_id: 'a1',
  name: 'Opdracht Alfa 2026',
  status: 'in_progress',
  client_name: 'Voorbeeldministerie',
  start_date: '2026-01-01',
  end_date: '2026-12-31',
};

afterEach(() => vi.unstubAllGlobals());

const cellTexts = (container: HTMLElement) =>
  [...container.querySelectorAll('nldd-text-cell')].map((cell) => cell.getAttribute('text'));

describe('OverviewPage', () => {
  it('asks for the current year by default', async () => {
    const fetchMock = respondWith({ year: 2026, rows: [] });
    renderApp(<OverviewPage />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(String((fetchMock.mock.calls as unknown[][])[0]?.[0])).toBe(`/api/overview?year=${currentYearChoice()}`);
  });

  it('shows the amounts the API sent, formatted and not recomputed', async () => {
    respondWith({ year: 2026, rows: [{ ...ROW, totals: TOTALS, pricing_error: null }], totals: TOTALS });
    const { container } = renderApp(<OverviewPage />);
    await waitFor(() => expect(container.querySelector('nldd-table')).not.toBeNull());

    const texts = cellTexts(container);
    expect(texts).toContain('Begroot');
    expect(texts.some((text) => text?.includes('187.800'))).toBe(true);
    expect(texts.some((text) => text?.includes('21.300'))).toBe(true);
    expect(container.querySelector('nldd-link')).toHaveAttribute('href', '/opdrachten/a1');
    expect(container.querySelector('nldd-badge')).toHaveAttribute('text', 'In uitvoering');
  });

  it('says an overrun in words', async () => {
    const over = { ...TOTALS, available_cents: -500000, overrun: true };
    respondWith({ year: 2026, rows: [{ ...ROW, totals: over }], totals: over });
    const { container } = renderApp(<OverviewPage />);
    await waitFor(() =>
      expect(container.querySelector('nldd-text-cell[supporting-text="Overschrijding"]')).not.toBeNull(),
    );
  });

  it('shows no amount columns to a reader who got none', async () => {
    respondWith({ year: 2026, rows: [{ ...ROW, totals: null }] });
    const { container } = renderApp(<OverviewPage />);
    await waitFor(() => expect(container.querySelector('nldd-table')).not.toBeNull());
    const texts = cellTexts(container);
    expect(texts).not.toContain('Begroot');
    expect(texts).toContain('Voorbeeldministerie');
  });

  it('explains an assignment that could not be priced', async () => {
    respondWith({
      year: 2027,
      rows: [{ ...ROW, totals: null, pricing_error: 'Er is geen actieve tarievenkaart voor 2027.' }],
      totals: { ...TOTALS, budgeted_cents: 0 },
    });
    const { container } = renderApp(<OverviewPage />);
    await waitFor(() =>
      expect(
        container.querySelector(
          'nldd-text-cell[supporting-text="Er is geen actieve tarievenkaart voor 2027."]',
        ),
      ).toHaveAttribute('text', 'Niet berekend'),
    );
  });

  it('has an empty state and keeps the heading', async () => {
    respondWith({ year: 2026, rows: [] });
    const { container } = renderApp(<OverviewPage />);
    await waitFor(() =>
      expect(
        container.querySelector('nldd-inline-dialog[text="Er zijn geen opdrachten om te tonen"]'),
      ).not.toBeNull(),
    );
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Stand van zaken');
  });

  it('shows the message of a failed request', async () => {
    respondWith({ title: 'Geen toegang', status: 403, detail: 'Je hebt hier geen toegang toe' }, 403);
    const { container } = renderApp(<OverviewPage />);
    await waitFor(() =>
      expect(
        container.querySelector('nldd-banner[text="Je hebt hier geen toegang toe"]'),
      ).not.toBeNull(),
    );
  });

  it('offers the whole period next to the years', () => {
    const options = yearOptions(new Date('2026-06-01'));
    expect(options.map((o) => o.label)).toEqual(['2024', '2025', '2026', '2027', '2028', 'Hele looptijd']);
    expect(options.at(-1)?.value).toBe('all');
  });
});
