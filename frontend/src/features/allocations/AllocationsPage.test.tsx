import { waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { renderApp } from '@/test/utils';
import { AllocationsPage } from './AllocationsPage';

function respondWith(body: unknown) {
  vi.stubGlobal(
    'fetch',
    vi.fn(() =>
      Promise.resolve(
        new Response(JSON.stringify(body), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    ),
  );
}

afterEach(() => vi.unstubAllGlobals());

const texts = (container: HTMLElement, selector: string) =>
  [...container.querySelectorAll(selector)].map((el) => el.getAttribute('text'));

describe('AllocationsPage', () => {
  it('shows a planner time and the signal, without amount or actions it may not take', async () => {
    respondWith({
      can_add: true,
      items: [
        {
          id: 'x1',
          person_id: 'p1',
          person_name: 'Voorbeeld Een',
          assignment_name: 'Opdracht Alfa',
          budget_line_id: 'l1',
          budget_line_description: 'Productmanager',
          start_date: '2026-01-01',
          end_date: '2026-12-31',
          fte_pct: '30.00',
          can_edit: true,
          category_mismatch: true,
        },
      ],
    });
    const { container } = renderApp(<AllocationsPage />);
    await waitFor(() => expect(container.querySelector('nldd-table')).not.toBeNull());

    const headers = texts(container, 'nldd-table-row[slot="header"] nldd-text-cell');
    expect(headers).toEqual(['Opdracht en regel', 'Periode', 'Inzet', 'Acties']);
    expect(texts(container, 'nldd-text-cell')).toContain('30%');
    expect(
      container.querySelector('nldd-text-cell[supporting-text*="andere categorie"]'),
    ).not.toBeNull();
    expect(container.querySelector('nldd-button[text="Nieuwe inzet"]')).not.toBeNull();
    expect(
      container.querySelector('nldd-button[accessible-label="Bewerk de inzet van Voorbeeld Een"]'),
    ).not.toBeNull();
  });

  it('shows a team member only names for a colleague', async () => {
    respondWith({
      can_add: false,
      items: [
        {
          id: 'x2',
          person_id: 'p2',
          person_name: 'Voorbeeld Twee',
          assignment_name: 'Opdracht Alfa',
          budget_line_id: 'l1',
          budget_line_description: 'Productmanager',
        },
      ],
    });
    const { container } = renderApp(<AllocationsPage />);
    await waitFor(() => expect(container.querySelector('nldd-table')).not.toBeNull());
    expect(texts(container, 'nldd-table-row[slot="header"] nldd-text-cell')).toEqual([
      'Opdracht en regel',
    ]);
    expect(container.querySelector('nldd-button[text="Nieuwe inzet"]')).toBeNull();
    expect(container.querySelector('nldd-button[text="Bewerk"]')).toBeNull();
  });

  it('has an empty state', async () => {
    respondWith({ can_add: false, items: [] });
    const { container } = renderApp(<AllocationsPage />);
    await waitFor(() =>
      expect(
        container.querySelector('nldd-inline-dialog[text="Er is geen inzet om te tonen"]'),
      ).not.toBeNull(),
    );
  });
});

describe('roles without inzet', () => {
  function respondPerPath(byPath: Record<string, unknown>) {
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL) => {
        const url = typeof input === 'string' ? input : input.toString();
        const match = Object.keys(byPath).find((path) => url.includes(path));
        return Promise.resolve(
          new Response(JSON.stringify(match ? byPath[match] : {}), {
            status: match ? 200 : 404,
            headers: { 'Content-Type': 'application/json' },
          }),
        );
      }),
    );
  }

  it('offers to open a vacancy for a role nobody fills', async () => {
    respondPerPath({
      '/api/allocations': { can_add: true, items: [] },
      '/api/vacancies/unfilled-roles': [
        {
          budget_line_id: 'l9',
          assignment_id: 'a1',
          assignment_name: 'Opdracht Delta',
          description: 'Developer',
          role: 'Developer',
          fte: '1',
          unfilled_fte: '1',
          start_date: '2026-07-01',
          end_date: '2027-06-30',
        },
      ],
    });
    const { container } = renderApp(<AllocationsPage />);
    await waitFor(() =>
      expect(container.querySelector('nldd-list-item[href="/vacatures?rol=l9"]')).not.toBeNull(),
    );
    const cell = container.querySelector('nldd-list-item[href="/vacatures?rol=l9"] nldd-text-cell');
    expect(cell).toHaveAttribute('text', 'Developer: maak een vacature');
    expect(cell).toHaveAttribute('overline', 'Opdracht Delta');
  });

  it('shows nothing when the list is not for this reader', async () => {
    respondPerPath({ '/api/allocations': { can_add: false, items: [] } });
    const { container } = renderApp(<AllocationsPage />);
    await waitFor(() => expect(container.querySelector('nldd-inline-dialog')).not.toBeNull());
    expect(container.querySelector('nldd-list')).toBeNull();
  });
});
