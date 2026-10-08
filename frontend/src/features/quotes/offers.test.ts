import { describe, expect, it } from 'vitest';
import type { QuoteOffer, QuoteSummary } from './api';
import { standing } from '@/features/assignments/standing';
import {
  invitationMessage,
  linkWorks,
  listedOffers,
  offerState,
  offerTitle,
  primaryAction,
  quoteSteps,
} from './offers';

const QUOTE: QuoteSummary = {
  id: 'q-1',
  uri: 'https://grip.example/id/offerte/q-1',
  reference: 'VG-2026-0007',
  assignment_id: 'a-1',
  status: 'issued',
  issued_at: '2026-02-01T09:00:00Z',
  issued_by_name: null,
};

function link(state: string, overrides: Partial<QuoteOffer> = {}): QuoteOffer {
  return {
    id: 'o-1',
    channel: 'signing_link',
    recipient: 'tekenaar@opdrachtgever.example',
    offered_at: '2026-02-02T10:00:00Z',
    invitation: {
      id: 'i-1',
      signing_path: '/tekenen/q-1',
      expires_at: '2026-03-04T10:00:00Z',
      opened_at: state === 'opened' ? '2026-02-03T08:30:00Z' : null,
      used_at: state === 'signed' ? '2026-02-04T08:30:00Z' : null,
      withdrawn_at: state === 'withdrawn' ? '2026-02-05T08:30:00Z' : null,
      state,
    },
    ...overrides,
  };
}

const DOCUMENT: QuoteOffer = {
  id: 'o-2',
  channel: 'document',
  offered_at: '2026-02-03T10:00:00Z',
};

describe('quoteSteps', () => {
  it('puts a fresh quote at offering', () => {
    expect(quoteSteps(QUOTE, []).map((step) => step.status)).toEqual(['past', 'current', 'future']);
  });

  it('waits for the decision once offered', () => {
    expect(quoteSteps(QUOTE, [DOCUMENT]).map((step) => step.status)).toEqual([
      'past',
      'past',
      'current',
    ]);
  });

  it('names the decision once there is one', () => {
    const accepted = quoteSteps({ ...QUOTE, status: 'accepted' }, [DOCUMENT]);
    expect(accepted.map((step) => step.text)).toEqual(['Gemaakt', 'Aangeboden', 'Getekend']);
    expect(accepted.every((step) => step.status === 'past')).toBe(true);
    expect(quoteSteps({ ...QUOTE, status: 'rejected' }, [])[2]?.text).toBe('Afgewezen');
  });
});

describe('primaryAction', () => {
  it('is offering right after issuing', () => {
    expect(primaryAction(QUOTE, [])).toBe('offer');
  });

  it('is recording the signed copy when a document is all the client has', () => {
    expect(primaryAction(QUOTE, [DOCUMENT])).toBe('record-signed');
    expect(primaryAction(QUOTE, [link('withdrawn'), DOCUMENT])).toBe('record-signed');
  });

  it('is nothing while a signing link is open next to a document', () => {
    // The answer may come in by the link; recording a signed copy is in the menu.
    expect(primaryAction(QUOTE, [link('invited'), DOCUMENT])).toBeNull();
  });

  it('lists what still waits for an answer first', () => {
    const order = listedOffers([link('expired'), DOCUMENT]).map((offer) => offer.channel);
    expect(order).toEqual(['document', 'signing_link']);
  });

  it('is nothing while the client has the link, and nothing after a decision', () => {
    expect(primaryAction(QUOTE, [link('invited')])).toBeNull();
    expect(primaryAction({ ...QUOTE, status: 'accepted' }, [DOCUMENT])).toBeNull();
    expect(primaryAction({ ...QUOTE, status: 'superseded' }, [])).toBeNull();
  });
});

describe('offers in words', () => {
  it('says to whom a link went and where it stands', () => {
    expect(offerTitle(link('invited'))).toBe(
      'Met een tekenlink aan tekenaar@opdrachtgever.example',
    );
    expect(offerState(link('invited'), QUOTE)).toBe('Uitgenodigd, nog niet geopend');
    expect(offerState(link('opened'), QUOTE)).toMatch(/^Geopend op 3 feb 2026/);
    expect(offerState(link('withdrawn'), QUOTE)).toMatch(/^Tekenlink ingetrokken op/);
    expect(offerState(link('expired'), QUOTE)).toBe('Tekenlink verlopen op 4 mrt 2026');
    const signed = {
      ...QUOTE,
      status: 'accepted',
      acceptance: {
        form: 'signing_link',
        signed_at: '2026-02-04T08:30:00Z',
        signer_name: 'Tekenaar Voorbeeld',
      },
    };
    expect(offerState(link('signed'), signed)).toMatch(
      /^Getekend op 4 feb 2026.* door Tekenaar Voorbeeld$/,
    );
  });

  it('gives the delivery of an offer to the client’s own grip', () => {
    const offer = {
      id: 'o-3',
      channel: 'client_instance',
      offered_at: '2026-02-02T10:00:00Z',
    };
    expect(offerState({ ...offer, delivery: 'pending' }, QUOTE)).toBe(
      'Onderweg naar de opdrachtgever',
    );
    expect(offerState({ ...offer, delivery: 'sent' }, QUOTE)).toBe(
      'Afgeleverd bij de opdrachtgever',
    );
    expect(offerState({ ...offer, delivery: 'refused' }, QUOTE)).toBe(
      'Niet afgeleverd bij de opdrachtgever',
    );
  });

  it('shows one entry per signing link, the latest offer on it', () => {
    const again = link('opened', {
      id: 'o-9',
      offered_at: '2026-02-06T10:00:00Z',
    });
    const listed = listedOffers([link('invited'), DOCUMENT, again]);
    expect(listed.map((offer) => offer.id)).toEqual(['o-9', 'o-2']);
  });

  it('knows when a link still opens the quote', () => {
    expect(linkWorks(link('invited'))).toBe(true);
    expect(linkWorks(link('opened'))).toBe(true);
    for (const state of ['signed', 'expired', 'withdrawn']) {
      expect(linkWorks(link(state))).toBe(false);
    }
    expect(linkWorks(DOCUMENT)).toBe(false);
  });
});

describe('invitationMessage', () => {
  it('is ready to paste: what, where, how to log in, until when', () => {
    const text = invitationMessage({
      reference: 'VG-2026-0007',
      name: 'Opdracht Alfa',
      link: 'https://grip.example/tekenen/q-1',
      email: 'tekenaar@opdrachtgever.example',
      expiresAt: '2026-03-04T10:00:00Z',
    });
    expect(text).toContain('offerte VG-2026-0007 voor Opdracht Alfa');
    expect(text).toContain('https://grip.example/tekenen/q-1');
    expect(text).toContain('tekenaar@opdrachtgever.example');
    expect(text).toContain('tot en met 4 mrt 2026');
  });
});

describe('the card and the assignment read one position', () => {
  const FACTS = {
    phase: 'potential',
    status: 'quoted',
    mayAct: true,
    owners: 'Eigenaar Voorbeeld',
    budgetLines: 1,
    today: '2026-02-10',
  };
  const approvalState = (status: string, mayOffer = false) => ({
    quote_id: 'q-1',
    approval_required: true,
    status,
    may_offer: mayOffer,
    approver_available: true,
  });
  // Step of the assignment -> the step of the card that says the same.
  const SAME: Record<string, string> = {
    approval: 'Interne goedkeuring',
    offer: 'Aangeboden',
    agreement: 'Getekend of afgewezen',
  };
  const cases: [string, QuoteOffer[], ReturnType<typeof approvalState> | null][] = [
    ['made, not offered', [], null],
    ['offered by link', [link('invited')], null],
    ['offered as a document', [DOCUMENT], null],
    ['needs approval, not asked', [], approvalState('none')],
    ['approval asked', [], approvalState('requested')],
    ['approved, not offered', [], approvalState('approved', true)],
    ['approved and offered', [link('opened')], approvalState('approved', true)],
  ];

  it.each(cases)('%s', (_name, offers, approval) => {
    const assignment = standing({
      ...FACTS,
      quotes: [
        {
          status: QUOTE.status,
          issued_at: QUOTE.issued_at,
          ...(approval ? { approval: approval.status } : {}),
        },
      ],
      offers: offers.map((offer) => ({
        channel: offer.channel,
        offered_at: offer.offered_at,
        invitationState: offer.invitation?.state ?? null,
      })),
    });
    const card = quoteSteps(QUOTE, offers, approval);
    const currentOnCard = card.find((step) => step.status === 'current')?.text;
    expect(currentOnCard).toBe(SAME[assignment?.current ?? '']);
    // The approval step is on both bars or on neither.
    expect(card.some((step) => step.text === 'Interne goedkeuring')).toBe(
      assignment?.steps.some((step) => step.key === 'approval'),
    );
  });

  it('agrees on a quote that was sent back: a new quote is the step', () => {
    const approval = approvalState('sent_back');
    const assignment = standing({
      ...FACTS,
      quotes: [{ status: 'issued', issued_at: QUOTE.issued_at, approval: 'sent_back' }],
      offers: [],
    });
    expect(assignment?.current).toBe('quote');
    expect(primaryAction(QUOTE, [], approval)).toBe('new-quote');
  });
});
