import { describe, expect, it } from 'vitest';
import { standing, type StandingFacts } from './standing';

const facts = (overrides: Partial<StandingFacts> = {}): StandingFacts => ({
  phase: 'potential',
  status: 'draft',
  mayAct: true,
  owners: 'Voorbeeld Eigenaar',
  today: '2026-10-08',
  ...overrides,
});
const issued = { status: 'issued', issued_at: '2026-10-01T09:00:00Z', valid_until: '2026-11-30' };
const states = (result: ReturnType<typeof standing>) =>
  result?.steps.map((step) => `${step.key}:${step.state}`);

describe('standing', () => {
  it('has nothing to say once the assignment is agreed', () => {
    expect(standing(facts({ phase: 'active', status: 'accepted' }))).toBeNull();
  });

  it('starts at the budget', () => {
    const result = standing(facts({ budgetLines: 0, quotes: [] }));
    expect(states(result)).toEqual(['budget:current', 'quote:future', 'offer:future', 'agreement:future']);
    expect(result?.action).toEqual({ text: 'Maak de begroting', tab: 'budget' });
  });

  it('moves to the quote once there is a budget', () => {
    const result = standing(facts({ budgetLines: 2, quotes: [] }));
    expect(result?.current).toBe('quote');
    expect(result?.advice).toBe('De begroting staat. Maak er een offerte van.');
  });

  it('asks to offer a quote that was made and not offered', () => {
    const result = standing(facts({ status: 'quoted', budgetLines: 2, quotes: [issued], offers: [] }));
    expect(states(result)).toEqual(['budget:done', 'quote:done', 'offer:current', 'agreement:future']);
    expect(result?.action?.text).toBe('Bied de offerte aan');
  });

  it('waits for the client once offered, and says how and since when', () => {
    const result = standing(
      facts({
        status: 'quoted',
        budgetLines: 2,
        quotes: [issued],
        offers: [
          { channel: 'document', offered_at: '2026-10-02T10:00:00Z' },
          { channel: 'signing_link', offered_at: '2026-10-08T10:00:00Z', invitationState: 'invited' },
        ],
      }),
    );
    expect(states(result)).toEqual(['budget:done', 'quote:done', 'offer:done', 'agreement:current']);
    expect(result?.advice).toBe('Aangeboden met een tekenlink op 8 okt 2026; nog geen reactie.');
    expect(result?.action?.text).toBe('Open de offerte');
  });

  it('offers to record the signed document when the quote went as a document', () => {
    const result = standing(
      facts({ quotes: [issued], offers: [{ channel: 'document', offered_at: '2026-10-02T10:00:00Z' }] }),
    );
    expect(result?.advice).toBe('Aangeboden als document op 2 okt 2026; nog geen reactie.');
    expect(result?.action?.text).toBe('Leg het getekende akkoord vast');
  });

  it('says that the client opened the signing link', () => {
    const result = standing(
      facts({
        quotes: [issued],
        offers: [{ channel: 'signing_link', offered_at: '2026-10-08T10:00:00Z', invitationState: 'opened' }],
      }),
    );
    expect(result?.advice).toContain('geopend, nog niet getekend');
  });

  it('keeps a verbal yes inside the last step', () => {
    const result = standing(facts({ status: 'verbally_agreed', quotes: [issued], offers: [] }));
    expect(result?.current).toBe('agreement');
    expect(result?.advice).toContain('mondeling');
  });

  it('shows internal approval as a step only when the quote has one', () => {
    const pending = standing(facts({ quotes: [{ ...issued, approval: 'requested' }], offers: [] }));
    expect(states(pending)).toEqual([
      'budget:done',
      'quote:done',
      'approval:current',
      'offer:future',
      'agreement:future',
    ]);
    const approved = standing(facts({ quotes: [{ ...issued, approval: 'approved' }], offers: [] }));
    expect(approved?.current).toBe('offer');
    expect(approved?.steps.map((step) => step.key)).toContain('approval');
    // Needed and not asked yet: asking is the step, in the server's words when it gives them.
    const needed = standing(
      facts({ quotes: [{ ...issued, approval: 'none', blockedMessage: 'Vanaf € 100.000 is intern akkoord nodig.' }], offers: [] }),
    );
    expect(needed?.current).toBe('approval');
    expect(needed?.advice).toBe('Vanaf € 100.000 is intern akkoord nodig.');
    expect(needed?.action?.text).toBe('Vraag intern akkoord');
    // No approval asked of this quote: no step.
    const plainQuote = standing(facts({ quotes: [issued], offers: [] }));
    expect(plainQuote?.steps.map((step) => step.key)).not.toContain('approval');
  });

  it('goes back to the quote when it was sent back internally', () => {
    const result = standing(facts({ quotes: [{ ...issued, approval: 'sent_back' }], offers: [] }));
    expect(result?.current).toBe('quote');
    expect(result?.advice).toContain('intern teruggestuurd');
  });

  it('asks for a new quote when the last one expired or was rejected', () => {
    const expired = standing(facts({ budgetLines: 2, quotes: [{ ...issued, valid_until: '2026-10-01' }] }));
    expect(expired?.current).toBe('quote');
    expect(expired?.advice).toBe('De offerte is verlopen op 1 okt 2026. Maak een nieuwe offerte.');
    const rejected = standing(facts({ budgetLines: 2, quotes: [{ ...issued, status: 'rejected' }] }));
    expect(rejected?.current).toBe('quote');
    expect(rejected?.advice).toContain('afgewezen');
  });

  it('says less, never something else, when the quotes or offers are not known', () => {
    // Only the assignment itself is known: a quote exists, nothing about offers.
    const result = standing(facts({ status: 'quoted' }));
    expect(states(result)).toEqual(['budget:done', 'quote:done', 'offer:current', 'agreement:future']);
    expect(result?.advice).toBe('De offerte is gemaakt.');
    expect(result?.action?.text).toBe('Ga naar de offerte');
  });

  it('says whose turn it is to a reader who cannot take the step', () => {
    const result = standing(facts({ mayAct: false }));
    expect(result?.action).toBeNull();
    expect(result?.steps.every((step) => step.tab === undefined)).toBe(true);
    expect(result?.advice).toContain('Voorbeeld Eigenaar maakt eerst de begroting');
  });

  it('goes back to the quote when the budget moved after it was offered', () => {
    const result = standing(
      facts({
        status: 'quoted',
        budgetLines: 3,
        quotes: [issued],
        offers: [{ channel: 'signing_link', offered_at: '2026-10-08T10:00:00Z' }],
        budgetMoved: true,
      }),
    );
    expect(states(result)).toEqual(['budget:done', 'quote:current', 'offer:future', 'agreement:future']);
    expect(result?.advice).toContain('De offerte klopt niet meer');
    expect(result?.action).toEqual({ text: 'Maak een nieuwe offerte', tab: 'quote' });
  });
});
