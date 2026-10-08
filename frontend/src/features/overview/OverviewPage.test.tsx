import { screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { FIGURES, allText, mockApi } from '@/features/assignments/testing';
import { renderApp } from '@/test/utils';
import { OverviewPage } from './OverviewPage';
import { currentYearChoice, yearOptions } from './years';

afterEach(() => vi.unstubAllGlobals());

const ROW = {
  assignment_id: 'a1',
  name: 'Opdracht Alfa 2026',
  status: 'in_progress',
  phase: 'active',
  client_name: 'Voorbeeldministerie',
  start_date: '2026-01-01',
  end_date: '2026-12-31',
  figures: FIGURES,
  pricing_error: null,
  reference_month: '2026-02-01',
};
const PIPELINE = { ...FIGURES, budgeted_cents: 5000000, expected_total_cents: 5000000 };
const PROSPECT = {
  ...ROW,
  assignment_id: 'a2',
  name: 'Opdracht Epsilon 2027',
  status: 'quoted',
  phase: 'potential',
  figures: PIPELINE,
  reference_month: null,
};
const ZERO = { ...FIGURES, budgeted_cents: 0 };

const tables = (container: HTMLElement) =>
  [...container.querySelectorAll('nldd-table')].map((t) => t.getAttribute('accessible-label'));

describe('OverviewPage', () => {
  it('asks for the current year by default', async () => {
    const fetchMock = mockApi({ '/api/overview': { year: 2026, rows: [] } });
    renderApp(<OverviewPage />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(String((fetchMock.mock.calls as unknown[][])[0]?.[0])).toBe(
      `/api/overview?year=${currentYearChoice()}`,
    );
  });

  it('keeps pipeline apart from running work, each with its own subtotal', async () => {
    mockApi({
      '/api/overview': {
        year: 2026,
        rows: [PROSPECT, ROW],
        figures_active: FIGURES,
        figures_potential: PIPELINE,
        figures_closed: ZERO,
      },
    });
    const { container } = renderApp(<OverviewPage />);
    await waitFor(() => expect(container.querySelectorAll('nldd-table').length).toBe(2));
    // Running work first, then the pipeline; no table adds the two.
    expect(tables(container)).toEqual([
      'Lopende opdrachten, stand over 2026',
      'Potentiële opdrachten, stand over 2026',
    ].map((label) => label.replace('2026', currentYearChoice())));
    const [active, potential] = [...container.querySelectorAll('nldd-table')] as HTMLElement[];
    expect(allText(active!)).toContain('Opdracht Alfa 2026');
    expect(allText(active!)).not.toContain('Opdracht Epsilon 2027');
    expect(allText(active!)).toContain('Subtotaal lopende opdrachten');
    expect(allText(active!)).toContain('187.800');
    expect(allText(potential!)).toContain('Subtotaal potentiële opdrachten');
    expect(allText(potential!)).toContain('50.000');
    expect(allText(container)).toContain('tellen niet mee in de totalen van lopend werk');
    expect(allText(container)).not.toMatch(/\*\*Totaal\*\*/);
  });

  it('names the state of the money and gives each row its reference date', async () => {
    mockApi({ '/api/overview': { year: 2026, rows: [ROW], figures_active: FIGURES } });
    const { container } = renderApp(<OverviewPage />);
    await waitFor(() => expect(container.querySelector('nldd-table')).not.toBeNull());
    const text = allText(container);
    for (const label of ['Begroot', 'Gerealiseerd', 'Nog gepland', 'Verwacht totaal', 'Afwijking']) {
      expect(text).toContain(label);
    }
    expect(text).toContain('Stand t/m februari 2026');
    expect(container.querySelector('nldd-link')).toHaveAttribute('href', '/opdrachten/a1/financieel');
  });

  it('says an overrun in words', async () => {
    const over = { ...FIGURES, variance_cents: -500000, variance_pct: '-2.7', overrun: true };
    mockApi({ '/api/overview': { year: 2026, rows: [{ ...ROW, figures: over }], figures_active: over } });
    const { container } = renderApp(<OverviewPage />);
    await waitFor(() =>
      expect(container.querySelector('nldd-text-cell[supporting-text="Overschrijding"]')).not.toBeNull(),
    );
  });

  it('shows no amount columns to a reader who got none', async () => {
    mockApi({ '/api/overview': { year: 2026, rows: [{ ...ROW, figures: null }] } });
    const { container } = renderApp(<OverviewPage />);
    await waitFor(() => expect(container.querySelector('nldd-table')).not.toBeNull());
    const text = allText(container);
    expect(text).not.toContain('Begroot');
    expect(text).not.toContain('€');
    expect(text).toContain('Voorbeeldministerie');
    expect(container.querySelector('nldd-link')).toHaveAttribute('href', '/opdrachten/a1');
  });

  it('explains an assignment that could not be priced', async () => {
    mockApi({
      '/api/overview': {
        year: 2027,
        rows: [{ ...ROW, figures: null, pricing_error: 'Er is geen actieve tarievenkaart voor 2027.' }],
        figures_active: ZERO,
      },
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
    mockApi({ '/api/overview': { year: 2026, rows: [] } });
    const { container } = renderApp(<OverviewPage />);
    await waitFor(() =>
      expect(
        container.querySelector('nldd-inline-dialog[text="Er zijn geen opdrachten om te tonen"]'),
      ).not.toBeNull(),
    );
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Stand van zaken');
  });

  it('offers the whole period next to the years', () => {
    const options = yearOptions(new Date('2026-06-01'));
    expect(options.map((o) => o.label)).toEqual(['2024', '2025', '2026', '2027', '2028', 'Hele looptijd']);
    expect(options.at(-1)?.value).toBe('all');
  });
});
