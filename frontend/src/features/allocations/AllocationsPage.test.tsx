import { fireEvent, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { allText, mockApi } from '@/features/assignments/testing';
import { renderApp } from '@/test/utils';
import { AllocationsPage } from './AllocationsPage';
import { board } from './board/testing';

afterEach(() => vi.unstubAllGlobals());

const OPTIONS = {
  people: [{ id: 'p1', name: 'Voorbeeld Een' }],
  lines: [
    { budget_line_id: 'l1', assignment_id: 'a1', assignment_name: 'Opdracht Alfa', description: 'Productmanager' },
  ],
};

function renderPage(data = board(), vacancyRoles: unknown = [], options: unknown = OPTIONS) {
  const fetchMock = mockApi({
    '/api/allocations/board': data,
    '/api/vacancies/unfilled-roles': vacancyRoles,
    '/api/allocations/options': options,
  });
  return { ...renderApp(<AllocationsPage />), fetchMock };
}

const grid = async (container: HTMLElement) => {
  await waitFor(() => expect(container.querySelector('table[role="grid"]')).not.toBeNull());
  return container.querySelector('table[role="grid"]') as HTMLTableElement;
};

describe('Inzet board', () => {
  it('is a table: a column header per month, a row header per person, text in every cell', async () => {
    const { container } = renderPage();
    const table = await grid(container);
    expect(table.querySelectorAll('thead th[scope="col"]')).toHaveLength(13);
    expect(table.querySelector('th[aria-current="date"]')).toHaveTextContent('nu');
    const rows = [...table.querySelectorAll('tbody tr:not(.grip-board__group)')];
    expect(rows.map((row) => row.querySelector('th[scope="row"] .grip-board__name')?.textContent)).toEqual([
      'Ontwerper',
      'Voorbeeld Een',
      'Voorbeeld Twee',
    ]);
    for (const cell of table.querySelectorAll('td')) {
      expect(cell.querySelector('.grip-board__sr-only')?.textContent).not.toBe('');
    }
  });

  it('has one page title and quiet row labels', async () => {
    const { container } = renderPage();
    await grid(container);
    expect(container.querySelectorAll('h1')).toHaveLength(1);
    expect(container.querySelectorAll('h2, h3')).toHaveLength(0);
    expect(container.querySelector('.grip-board__attention')).toHaveTextContent('Boven 100% in apr, mei');
    expect(container.querySelector('.grip-board__summary')).not.toBeNull();
  });

  it('draws each allocation as a bar over its months, tentative and open roles marked', async () => {
    const { container } = renderPage();
    const table = await grid(container);
    const bars = [...table.querySelectorAll<HTMLElement>('.grip-board__bar')];
    expect(bars).toHaveLength(4);
    const firm = table.querySelector<HTMLElement>('[data-bar="x1"]')!;
    expect(firm.style.getPropertyValue('--span')).toBe('6');
    expect(firm.querySelector('.grip-board__bar-closed')).not.toBeNull();
    const tentative = table.querySelector('[data-bar="x2"]')!;
    expect(tentative).toHaveAttribute('data-tentative');
    expect(tentative).toHaveAttribute('data-mark', '≠');
    expect(tentative.getAttribute('title')).toContain('onder voorbehoud');
    expect(table.querySelector('[data-bar="role-l9"]')).toHaveAttribute('data-open');
    expect(table.querySelector('[data-bar="x3"]')).toHaveAttribute('data-clipped-start');
  });

  it('makes a total loud only above 100 percent or with room ahead', async () => {
    const { container } = renderPage();
    const table = await grid(container);
    const states = [...table.querySelectorAll('tbody tr')]
      .find((row) => row.textContent?.includes('Voorbeeld Een'))!
      .querySelectorAll('.grip-board__total');
    expect([...states].map((total) => total.getAttribute('data-state'))).toEqual([
      'quiet', 'quiet', 'quiet', 'over', 'over', 'room', 'room', 'room', 'room', 'room', 'room', 'room',
    ]);
  });

  it('shows no amount anywhere', async () => {
    const { container } = renderPage();
    await grid(container);
    expect(allText(container)).not.toContain('€');
  });

  it('is one tab stop, walked with the arrow keys', async () => {
    const { container } = renderPage();
    const table = await grid(container);
    expect(table.querySelectorAll('td[tabindex="0"]')).toHaveLength(1);
    const first = table.querySelector<HTMLElement>('td[data-cell="0-0"]')!;
    first.focus();
    fireEvent.keyDown(first, { key: 'ArrowRight' });
    fireEvent.keyDown(document.activeElement!, { key: 'ArrowDown' });
    expect(document.activeElement).toHaveAttribute('data-cell', '1-1');
    expect(table.querySelectorAll('td[tabindex="0"]')).toHaveLength(1);
    fireEvent.keyDown(document.activeElement!, { key: 'End' });
    expect(document.activeElement).toHaveAttribute('data-cell', '1-11');
  });

  it('lists what is in a cell on Enter, with a way to act on every bar', async () => {
    const { container } = renderPage();
    const table = await grid(container);
    const cell = table.querySelector<HTMLElement>('td[data-cell="1-3"]')!;
    cell.focus();
    fireEvent.keyDown(cell, { key: 'Enter' });
    await waitFor(() =>
      expect(container.querySelector('[role="region"][aria-label="Inzet in de gekozen maand"]')).not.toBeNull(),
    );
    const panel = container.querySelector('[role="region"]') as HTMLElement;
    expect(panel.querySelector('nldd-title')).toHaveAttribute('text', 'Voorbeeld Een, april 2026');
    const buttons = [...panel.querySelectorAll('nldd-button')].map((b) => b.getAttribute('text'));
    expect(buttons).toEqual(['Bewerk', 'Bewerk', 'Nieuwe inzet vanaf april 2026']);
    expect(cell).toHaveAttribute('aria-selected', 'true');
  });

  it('opens the sheet from a bar, and says which months are closed', async () => {
    const { container } = renderPage();
    const table = await grid(container);
    fireEvent.click(table.querySelector('[data-bar="x1"]')!);
    await waitFor(() => expect(document.querySelector('nldd-sheet[open]')).not.toBeNull());
    const sheet = document.querySelector('nldd-sheet') as HTMLElement;
    expect(sheet.querySelector('nldd-top-title-bar')).toHaveAttribute(
      'text',
      'Inzet van Voorbeeld Een bewerken',
    );
    expect(sheet.querySelector('nldd-banner')).toHaveAttribute('text', 'Vastgesteld t/m februari 2026');
  });

  it('proposes a new inzet from an empty stretch, starting that month', async () => {
    const { container } = renderPage();
    const table = await grid(container);
    await waitFor(() =>
      expect(container.querySelector('nldd-button[text="Nieuwe inzet"]')).not.toBeNull(),
    );
    fireEvent.click(table.querySelector('td[data-cell="1-8"]')!);
    await waitFor(() => expect(document.querySelector('nldd-sheet[open]')).not.toBeNull());
    const sheet = document.querySelector('nldd-sheet') as HTMLElement;
    expect(sheet.querySelector('nldd-top-title-bar')).toHaveAttribute('text', 'Nieuwe inzet');
    expect(sheet.querySelector('nldd-date-field')).toHaveAttribute('value', '2026-09-01');
  });

  it('does not open a sheet for a bar the reader may not change', async () => {
    const { container } = renderPage();
    const table = await grid(container);
    fireEvent.click(table.querySelector('[data-bar="x3"]')!);
    expect(document.querySelector('nldd-sheet[open]')).toBeNull();
  });

  it('offers a vacancy for an open role only when the vacancy module allows it', async () => {
    const withLink = renderPage(board(), [{ budget_line_id: 'l9' }]);
    await waitFor(() =>
      expect(withLink.container.querySelector('nldd-link[text="Open een vacature"]')).not.toBeNull(),
    );
    withLink.unmount();
    const without = renderPage(board(), []);
    await grid(without.container);
    expect(without.container.querySelector('nldd-link[text="Open een vacature"]')).toBeNull();
  });

  it('keeps filters and actions in one toolbar and has no add button for a reader', async () => {
    const { container } = renderPage(board({ can_add: false }));
    await grid(container);
    const toolbar = container.querySelector('nldd-toolbar')!;
    expect([...toolbar.querySelectorAll('nldd-dropdown')].map((d) => d.getAttribute('accessible-label'))).toEqual([
      'Weergave',
      'Toon',
    ]);
    expect([...toolbar.querySelectorAll('nldd-button')].map((b) => b.getAttribute('text'))).toEqual([
      'Eerdere maanden',
      'Latere maanden',
    ]);
  });

  it('switches to assignments as rows without throwing', async () => {
    const { container } = renderPage();
    await grid(container);
    container
      .querySelector('nldd-dropdown[accessible-label="Weergave"]')
      ?.dispatchEvent(new CustomEvent('change', { detail: { value: 'assignment' } }));
    await waitFor(() =>
      expect(container.querySelector('thead th[scope="col"]')).toHaveTextContent('Opdracht en rol'),
    );
    expect([...container.querySelectorAll('.grip-board__group th')].map((th) => th.textContent)).toEqual([
      'Opdracht Alfa',
      'Opdracht Epsilon',
    ]);
    expect(container.querySelector('nldd-dropdown[accessible-label="Toon"]')).toBeNull();
  });

  it('asks for earlier months from the first month on screen', async () => {
    const { container, fetchMock } = renderPage();
    await grid(container);
    container.querySelector('nldd-button[text="Eerdere maanden"]')?.dispatchEvent(new Event('click'));
    await waitFor(() =>
      expect(
        (fetchMock.mock.calls as unknown[][]).some((call) => String(call[0]).includes('start=2025-10')),
      ).toBe(true),
    );
  });

  it('has an empty state', async () => {
    const { container } = renderPage(board({ persons: [], open_roles: [] }));
    await waitFor(() =>
      expect(
        container.querySelector('nldd-inline-dialog[text="Er is geen inzet om te tonen"]'),
      ).not.toBeNull(),
    );
  });

  it('does not offer a new inzet when there is no role to put someone on', async () => {
    const { container } = renderPage(board(), [], { people: [], lines: [] });
    const table = await grid(container);
    expect(container.querySelector('nldd-button[text="Nieuwe inzet"]')).toBeNull();
    fireEvent.click(table.querySelector('td[data-cell="1-8"]')!);
    expect(document.querySelector('nldd-sheet[open]')).toBeNull();
  });
});
