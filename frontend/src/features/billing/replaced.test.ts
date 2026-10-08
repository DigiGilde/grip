import { describe, expect, it } from 'vitest';
import { replacedText, replacesText } from './replaced';

const again = { month_label: 'februari 2026', delivery_id: 'd2', reference: 'O-12/2026-02-2' };

describe('a month delivered again', () => {
  it('says the first request is not to be invoiced any more', () => {
    expect(replacedText([{ ...again, amount_cents: 3_290_000 }], 0)).toBe(
      'Februari 2026 is opnieuw aangeleverd in factuurverzoek O-12/2026-02-2. Factureer dit verzoek niet meer.',
    );
  });

  it('says what still counts when only one month of a quarter was replaced', () => {
    const text = replacedText(
      [{ ...again, month_label: 'maart 2026', amount_cents: 100 }],
      2_880_000,
    );
    expect(text).toContain('Maart 2026 is opnieuw aangeleverd');
    expect(text).toContain('Van dit verzoek telt nog');
    expect(text).toContain('28.800');
  });

  it('names what a request replaces in the words of its document', () => {
    const text = replacesText({
      month_label: 'februari 2026',
      reference: 'O-12/2026-02',
      amount_cents: 3_290_000,
      difference_cents: -325_000,
    });
    expect(text).toContain('Dit verzoek vervangt februari 2026 uit factuurverzoek O-12/2026-02');
    expect(text).toContain('Het verschil is');
  });
});
