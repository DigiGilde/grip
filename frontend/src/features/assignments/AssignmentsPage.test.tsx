import { waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { mockApi, texts } from '@/features/team/ui/testing';
import { renderApp } from '@/test/utils';
import { AssignmentsPage } from './AssignmentsPage';
import { assignment } from './testing';

afterEach(() => vi.unstubAllGlobals());

const LIST = {
  items: [
    assignment({ id: 'a-1', name: 'Opdracht Alfa 2026', phase: 'closed', status: 'completed' }),
  ],
  total: 300,
  page: 2,
  page_size: 50,
  counts: { potential: 40, active: 60, closed: 300 },
  can_create: true,
};

async function renderList(body: object, path: string, courses: object[] = []) {
  const api = mockApi({ '/api/assignments': body, '/api/tasks/courses': { items: courses } });
  const view = renderApp(<AssignmentsPage />, { path });
  await waitFor(() => expect(view.container.querySelector('nldd-list')).not.toBeNull());
  return { container: view.container, calls: api.calls };
}

function narrowWindow(narrow: boolean) {
  vi.stubGlobal(
    'matchMedia',
    vi.fn().mockImplementation(() => ({
      matches: narrow,
      addEventListener: () => {},
      removeEventListener: () => {},
    })),
  );
}

describe('AssignmentsPage', () => {
  it('asks the server for one view, one page and the words searched for', async () => {
    const { calls } = await renderList(LIST, '/opdrachten?weergave=afgesloten&pagina=2&zoek=alfa');
    const asked = calls.find((call) => call.startsWith('/api/assignments?'));
    const params = new URLSearchParams(asked?.split('?')[1]);
    expect(Object.fromEntries(params)).toEqual({
      phase: 'closed',
      page: '2',
      page_size: '50',
      q: 'alfa',
    });
  });

  it('shows the counts of the server on the tabs and keeps the search across them', async () => {
    const { container } = await renderList(LIST, '/opdrachten?weergave=afgesloten&zoek=alfa');
    const tabs = [...container.querySelectorAll('.thing-tabs nldd-menu-bar-item')];
    expect(tabs.map((tab) => tab.getAttribute('text'))).toEqual([
      'Potentieel (40)',
      'Lopend (60)',
      'Afgesloten (300)',
    ]);
    // Another view starts at its first page, with the same words.
    expect(tabs.map((tab) => tab.getAttribute('href'))).toEqual([
      '/opdrachten?weergave=potentieel&zoek=alfa',
      '/opdrachten?zoek=alfa',
      '/opdrachten?weergave=afgesloten&zoek=alfa',
    ]);
  });

  it('keeps the views as a bar on a narrow screen, without the counts', async () => {
    narrowWindow(true);
    const { container } = await renderList(LIST, '/opdrachten');
    const tabs = [...container.querySelectorAll('.thing-tabs nldd-menu-bar-item')];
    expect(tabs.map((tab) => tab.getAttribute('text'))).toEqual([
      'Potentieel',
      'Lopend',
      'Afgesloten',
    ]);
    expect(container.querySelector('select, nldd-dropdown')).toBeNull();
  });

  it('shows each assignment as a row: what, for whom and when, and where it stands', async () => {
    const running = assignment({ id: 'a-1', name: 'Opdracht Alfa 2026' });
    const course = {
      case_kind: 'assignment',
      case_id: 'a-1',
      course: {
        key: 'assignment',
        label: 'Opdracht',
        steps: [],
        current_label: 'Uitvoeren',
        next: { mine: true, headline: 'Sluit maart 2026 af', sentence: '' },
      },
    };
    const { container } = await renderList(
      { ...LIST, items: [running], total: 1, counts: { potential: 0, active: 1, closed: 0 } },
      '/opdrachten',
      [course],
    );
    expect(container.querySelector('nldd-table')).toBeNull();
    expect(container.querySelector('nldd-list')).toHaveAttribute('accessible-label', 'Lopend');
    const row = container.querySelector('nldd-list-item');
    expect(row).toHaveAttribute('href', '/opdrachten/a-1');
    await waitFor(() =>
      expect(row?.querySelector('nldd-text-cell')?.getAttribute('supporting-text')).toBe(
        'Voorbeeldministerie · 1 jan 2026 t/m 31 dec 2026 · Jij: sluit maart 2026 af',
      ),
    );
    expect(row?.querySelector('nldd-text-cell')).toHaveAttribute('text', 'Opdracht Alfa 2026');
    // The view says it is running, so the row does not say it again.
    expect(row?.querySelector('nldd-badge')).toBeNull();
  });

  it('names the amount of a potential assignment at the end of its row', async () => {
    const potential = assignment({
      id: 'a-2',
      name: 'Opdracht Beta 2026',
      phase: 'potential',
      status: 'quoted',
      pipeline_amount_cents: 1250000,
      pipeline_amount_source: 'quote',
    });
    const { container } = await renderList(
      { ...LIST, items: [potential], total: 1, counts: { potential: 1, active: 0, closed: 0 } },
      '/opdrachten?weergave=potentieel',
    );
    const row = container.querySelector('nldd-list-item');
    expect(row?.textContent).toContain('12.500');
    expect(row?.querySelector('nldd-text-cell')?.getAttribute('supporting-text')).toContain(
      'bedrag uit de laatste offerte',
    );
    expect(row?.querySelector('nldd-badge')).toHaveAttribute('text', 'Offerte gemaakt');
  });

  it('says which rows these are and links to the other pages', async () => {
    const { container } = await renderList(LIST, '/opdrachten?weergave=afgesloten&pagina=2');
    expect(container.querySelector('[data-page-range]')).toHaveTextContent(
      '51 tot en met 100 van 300 opdrachten',
    );
    expect(container.querySelector('nldd-pagination')).toHaveAttribute('total', '6');
  });

  it('says so when the search finds nothing', async () => {
    mockApi({
      '/api/assignments': {
        ...LIST,
        items: [],
        total: 0,
        counts: { potential: 0, active: 0, closed: 0 },
      },
    });
    const { container } = renderApp(<AssignmentsPage />, { path: '/opdrachten?zoek=bestaatniet' });
    await waitFor(() =>
      expect(texts(container, 'nldd-inline-dialog')).toContain(
        'Geen opdrachten gevonden voor "bestaatniet"',
      ),
    );
    expect(container.querySelector('nldd-pagination')).toBeNull();
  });

  it('asks nothing for the form until it is opened', async () => {
    const { container, calls } = await renderList(LIST, '/opdrachten');
    expect(calls.some((call) => call.includes('/api/organisations'))).toBe(false);
    expect(container.querySelector('nldd-button[text="Nieuwe opdracht"]')).toHaveAttribute(
      'appearance',
      'primary',
    );
    expect(document.body.querySelector('nldd-sheet')).toBeNull();
  });
});
