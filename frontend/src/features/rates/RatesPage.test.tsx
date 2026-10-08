import { waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { mockApi, texts } from '@/features/team/ui/testing';
import { renderApp } from '@/test/utils';
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

afterEach(() => vi.unstubAllGlobals());

async function renderRates(card: object, mayManage: boolean) {
  mockApi({ '/api/rates/cards': { items: [card], may_manage: mayManage } });
  const view = renderApp(<RatesPage />, { path: '/tarieven' });
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

  it('says so when there is no card yet', async () => {
    mockApi({ '/api/rates/cards': { items: [], may_manage: false } });
    const { container } = renderApp(<RatesPage />, { path: '/tarieven' });
    await waitFor(() =>
      expect(texts(container, 'nldd-inline-dialog')).toContain('Er zijn nog geen tarievenkaarten'),
    );
  });

  it('shows an error state when the request fails', async () => {
    mockApi({});
    const { container } = renderApp(<RatesPage />, { path: '/tarieven' });
    await waitFor(() =>
      expect(texts(container, 'nldd-inline-dialog')).toContain(
        'De gegevens konden niet worden geladen',
      ),
    );
  });
});
