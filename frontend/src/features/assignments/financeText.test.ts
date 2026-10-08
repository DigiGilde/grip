import { describe, expect, it } from 'vitest';
import type { Signal } from './financeApi';
import { nothingPlanned, rateCauseText, signalText } from './financeText';
import { plain } from './testing';

const signal = (overrides: Partial<Signal>): Signal => ({
  kind: 'x',
  budget_line_id: null,
  description: null,
  amount_cents: null,
  pct: null,
  count: null,
  months: [],
  ...overrides,
});

describe('signals in words', () => {
  it('says a naverrekening with its months, its cause and what is still to deliver', () => {
    const text = signalText(
      signal({
        kind: 'correction_due',
        description: 'een schaalwijziging',
        amount_cents: 600000,
        count: 2,
        months: ['2026-07-01', '2026-08-01'],
      }),
      '10',
    ).text;
    expect(plain(text)).toBe(
      'Naverrekening over juli en augustus door een schaalwijziging: € 6.000 nog aan te leveren bovenop wat al is aangeleverd',
    );
  });

  it('says which way the budget differs from the signed quote', () => {
    const higher = signalText(signal({ kind: 'budget_differs_from_agreed', amount_cents: -250000 }), '10');
    expect(plain(higher.text)).toBe('De begroting is € 2.500 hoger dan de getekende offerte');
    const lower = signalText(signal({ kind: 'budget_differs_from_agreed', amount_cents: 100000 }), '10');
    expect(plain(lower.text)).toBe('De begroting is € 1.000 lager dan de getekende offerte');
  });

  it('gives the cause of a rate difference with the person only to who got it', () => {
    const named = 'gepromoveerd per 1 juli 2026: vanaf dan categorie C, de regel is begroot op B';
    expect(
      rateCauseText({ rate_difference_notes: [named], rate_difference_signals: ['tariefwijziging per 1 juli 2026'] }),
    ).toBe('Gepromoveerd per 1 juli 2026: vanaf dan categorie C, de regel is begroot op B');
    expect(rateCauseText({ rate_difference_signals: ['tariefwijziging per 1 juli 2026'] })).toBe(
      'Tariefwijziging per 1 juli 2026',
    );
    expect(rateCauseText({})).toBe('');
  });

  it('does not call a budget without inzet room', () => {
    expect(nothingPlanned({ budgeted_cents: 100, expected_total_cents: 0 })).toBe(true);
    expect(nothingPlanned({ budgeted_cents: 100, expected_total_cents: 50 })).toBe(false);
    expect(nothingPlanned({ budgeted_cents: 0, expected_total_cents: 0 })).toBe(false);
  });
});
