import { fireEvent, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { mockApi, texts } from '@/features/team/ui/testing';
import { renderApp } from '@/test/utils';
import { AppRoutes } from '@/AppRoutes';
import { APP_ROUTES } from '@/routes';
import { RatesPage } from './RatesPage';

const CARD = {
  year: 2026,
  status: 'active',
  rate_bands: [
    { category: 'A', monthly_rate_cents: 900000 },
    { category: 'D', monthly_rate_cents: 1800000 },
  ],
  scale_bands: [
    { scale: 14, category: 'D' },
    { scale: 15, category: 'D' },
  ],
};

const PREVIEW = {
  copy_from: 2026,
  increase_pct: '5',
  rounding: 'euro',
  rates: [
    {
      category: 'D',
      old_monthly_rate_cents: 1800000,
      new_monthly_rate_cents: 1890000,
      difference_cents: 90000,
    },
  ],
};

afterEach(() => vi.unstubAllGlobals());

async function renderRates(card: object, mayManage: boolean) {
  mockApi({
    '/api/rates/cards': { items: [card], may_manage: mayManage, default_increase_pct: '5.00' },
    '/api/rates/indexation-preview': PREVIEW,
  });
  const view = renderApp(<RatesPage />, { path: '/beheer/tarieven' });
  await waitFor(() => expect(view.container.querySelector('nldd-table')).not.toBeNull());
  return view.container;
}

describe('RatesPage', () => {
  it('shows the rates and scales of the card to someone who may only read', async () => {
    const container = await renderRates(CARD, false);
    const cells = texts(container, 'nldd-table nldd-text-cell');
    expect(cells).toContain('14, 15');
    expect(cells.some((text) => text.includes('18.000'))).toBe(true);
    // A category without a rate says so instead of showing nothing.
    expect(cells).toContain('Niet ingevuld');
    expect(texts(container, 'nldd-button')).toEqual([]);
  });

  it('offers the edit actions to someone who manages rates', async () => {
    const container = await renderRates(CARD, true);
    const buttons = texts(container, 'nldd-button');
    expect(buttons).toContain('Nieuw jaar');
    expect(buttons).toContain('Sluit dit jaar');
    expect(buttons.filter((text) => text === 'Wijzig')).toHaveLength(7);
    expect(buttons).toContain('Schaal toevoegen');
  });

  it('locks a closed year until the manager asks to change it', async () => {
    const container = await renderRates({ ...CARD, status: 'closed' }, true);
    const buttons = texts(container, 'nldd-button');
    expect(buttons).toContain('Wijzig gesloten jaar');
    expect(buttons).not.toContain('Wijzig');
    expect(buttons).not.toContain('Schaal toevoegen');
    // The confirmation says that an audit row is kept.
    const dialog = document.body.querySelector('nldd-modal-dialog');
    expect(dialog?.getAttribute('supporting-text')).toContain('auditlog');
  });

  it('gives every row action a name that says what it acts on', async () => {
    const container = await renderRates(CARD, true);
    const labels = [...container.querySelectorAll('nldd-table nldd-button')].map((el) =>
      el.getAttribute('accessible-label'),
    );
    expect(labels).toContain('Wijzig het maandtarief van categorie D');
    expect(labels).toContain('Wijzig de categorie van schaal 14');
  });

  it('previews a new year with the default increase before anything is created', async () => {
    const calls: string[] = [];
    const container = await renderRates(CARD, true);
    const fetchMock = vi.mocked(fetch);
    const button = [...container.querySelectorAll('nldd-button')].find(
      (el) => el.getAttribute('text') === 'Nieuw jaar',
    );
    fireEvent.click(button as Element);

    const sheet = document.body
      .querySelector('nldd-top-title-bar[text="Nieuw jaar"]')
      ?.closest('nldd-sheet') as HTMLElement;
    await waitFor(() => expect(sheet.querySelector('nldd-table')).not.toBeNull());
    for (const call of fetchMock.mock.calls) calls.push(String(call[0]));
    const preview = new URL(
      calls.find((url) => url.includes('indexation-preview')) ?? '',
      'http://test',
    );
    expect(preview.searchParams.get('copy_from')).toBe('2026');
    expect(preview.searchParams.get('increase_pct')).toBe('5');
    expect(preview.searchParams.get('rounding')).toBe('euro');

    const cells = texts(sheet, 'nldd-table nldd-text-cell');
    expect(cells).toContain('Tarief 2026');
    expect(cells.some((text) => text.includes('18.000'))).toBe(true);
    expect(cells.some((text) => text.includes('18.900'))).toBe(true);
    expect(cells.some((text) => text.startsWith('+') && text.includes('900'))).toBe(true);
    // The rounding rule is a visible choice, not a hidden default.
    const options = [...sheet.querySelectorAll('option')].map((o) => o.textContent);
    expect(options).toEqual(expect.arrayContaining(["Hele euro's", 'Tientallen', 'Vijftigtallen']));
    // Nothing was created by looking.
    expect(fetchMock.mock.calls.every((call) => (call[1]?.method ?? 'GET') === 'GET')).toBe(true);
  });

  it('says so when there is no card yet', async () => {
    mockApi({
      '/api/rates/cards': { items: [], may_manage: false, default_increase_pct: '5.00' },
    });
    const { container } = renderApp(<RatesPage />, { path: '/beheer/tarieven' });
    await waitFor(() =>
      expect(texts(container, 'nldd-inline-dialog')).toContain('Er zijn nog geen tarievenkaarten'),
    );
  });

  it('shows an error state when the request fails', async () => {
    mockApi({});
    const { container } = renderApp(<RatesPage />, { path: '/beheer/tarieven' });
    await waitFor(() =>
      expect(texts(container, 'nldd-inline-dialog')).toContain(
        'De gegevens konden niet worden geladen',
      ),
    );
  });
});

describe('where the rate cards live', () => {
  it('is under Beheer, not in the main navigation', () => {
    expect(APP_ROUTES.map((route) => route.title)).not.toContain('Tarieven');
  });

  it.each(['/beheer/tarieven', '/tarieven'])('shows the screen at %s', async (path) => {
    mockApi({
      '/api/rates/cards': { items: [], may_manage: false, default_increase_pct: '5.00' },
    });
    const { container } = renderApp(<AppRoutes />, { path });
    await waitFor(() =>
      expect(texts(container, 'nldd-inline-dialog')).toContain('Er zijn nog geen tarievenkaarten'),
    );
    expect(container.querySelector('h1')?.textContent).toBe('Tarieven');
  });
});
