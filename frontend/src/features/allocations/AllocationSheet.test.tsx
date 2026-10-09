import { waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { allText, mockApi } from '@/features/assignments/testing';
import { renderApp } from '@/test/utils';
import { AllocationSheet } from './AllocationSheet';

afterEach(() => vi.unstubAllGlobals());

const line = (id: string, assignmentId: string, assignment: string, description: string) => ({
  budget_line_id: id,
  assignment_id: assignmentId,
  assignment_name: assignment,
  description,
  fte: '1.000',
  start_date: '2026-10-01',
  end_date: '2026-10-29',
});
const OPTIONS = {
  people: [{ id: 'p1', name: 'Voorbeeld Een' }],
  lines: [
    line('l1', 'a1', 'Opdracht Alfa', 'Adviseur'),
    line('l2', 'a2', 'Opdracht Beta', 'Productmanager'),
  ],
};

const options = () =>
  [...document.querySelectorAll('nldd-form-field[label="Begrotingsregel"] option')].map(
    (o) => o.textContent,
  );

describe('AllocationSheet', () => {
  it('offers only the lines of the assignment it is opened on, without its name, the single one chosen', async () => {
    const fetchMock = mockApi({ '/api/allocations/options': OPTIONS });
    renderApp(<AllocationSheet open session={1} assignmentId="a1" onClose={() => undefined} />);
    await waitFor(() => expect(options().length).toBe(2));
    expect(options().map((text) => text?.replace(/\u00a0|\u202f/g, ' '))).toEqual([
      'Kies een begrotingsregel',
      'Adviseur (1 FTE, 1 okt 2026 t/m 29 okt 2026)',
    ]);
    const calls = (fetchMock.mock.calls as unknown[][]).map((call) => String(call[0]));
    expect(calls).toContain('/api/allocations/options?assignment_id=a1');
    // One role: it is chosen, and the period follows it in one calm line.
    const select = document.querySelector('nldd-form-field[label="Begrotingsregel"] select');
    await waitFor(() => expect(select).toHaveValue('l1'));
    const sheet = document.querySelector('nldd-sheet') as HTMLElement;
    expect(allText(sheet).replace(/\u00a0|\u202f/g, ' ')).toContain(
      'Loopt mee met de regel: 1 okt 2026 t/m 29 okt 2026',
    );
    // An action, so a real button, not bare text.
    expect(sheet.querySelector('nldd-button[text="Afwijkende periode"]')).toHaveAttribute(
      'appearance',
      'secondary',
    );
  });

  it('on the board offers every line with its assignment, and says nothing about a period before a line is chosen', async () => {
    mockApi({ '/api/allocations/options': OPTIONS });
    renderApp(<AllocationSheet open session={1} onClose={() => undefined} />);
    await waitFor(() => expect(options().length).toBe(3));
    expect(options()[1]).toContain('Opdracht Alfa: Adviseur');
    const sheet = document.querySelector('nldd-sheet') as HTMLElement;
    expect(allText(sheet)).not.toContain('Loopt mee');
    expect(allText(sheet)).not.toContain('looptijd');
  });

  it('says before saving that the person ends up above 100 percent, and lets an inzet be removed', async () => {
    mockApi({
      '/api/allocations/load-preview': {
        person_name: 'Voorbeeld Een',
        over_months: [{ month: '2026-10-01', current_pct: '80.0', new_pct: '180.0' }],
      },
    });
    const allocation = {
      id: 'al1',
      person_id: 'p1',
      person_name: 'Voorbeeld Een',
      budget_line_id: 'l1',
      period_source: 'line',
      start_date: '2026-10-01',
      end_date: '2026-10-29',
      fte_pct: '100.00',
    } as unknown as Parameters<typeof AllocationSheet>[0]['allocation'];
    renderApp(
      <AllocationSheet open session={1} allocation={allocation} onClose={() => undefined} />,
    );
    const sheet = document.querySelector('nldd-sheet') as HTMLElement;
    await waitFor(() =>
      expect(
        sheet.querySelector(
          'nldd-banner[text="Voorbeeld Een komt boven 100% in oktober 2026 (180%)"]',
        ),
      ).not.toBeNull(),
    );
    // Proceeding is a deliberate act: the button says what is saved.
    expect(sheet.querySelector('nldd-button[type="submit"]')).toHaveAttribute(
      'text',
      'Bewaar boven 100%',
    );
    const remove = sheet.querySelector('nldd-menu-item[text="Verwijder de inzet"]');
    expect(remove).toHaveAttribute('destructive');
  });
});
