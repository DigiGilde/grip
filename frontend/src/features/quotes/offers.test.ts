import { describe, expect, it } from 'vitest';
import type { QuoteOffer, QuoteSummary } from './api';
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

const DOCUMENT: QuoteOffer = { id: 'o-2', channel: 'document', offered_at: '2026-02-03T10:00:00Z' };

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
    expect(accepted.map((step) => step.text)).toEqual(['Uitgegeven', 'Aangeboden', 'Getekend']);
    expect(accepted.every((step) => step.status === 'past')).toBe(true);
    expect(quoteSteps({ ...QUOTE, status: 'rejected' }, [])[2]?.text).toBe('Afgewezen');
  });
});

describe('primaryAction', () => {
  it('is offering right after issuing', () => {
    expect(primaryAction(QUOTE, [])).toBe('offer');
  });

  it('is recording the signed copy when the quote went out as a document', () => {
    expect(primaryAction(QUOTE, [link('invited'), DOCUMENT])).toBe('record-signed');
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
      acceptance: { form: 'signing_link', signed_at: '2026-02-04T08:30:00Z', signer_name: 'Tekenaar Voorbeeld' },
    };
    expect(offerState(link('signed'), signed)).toMatch(/^Getekend op 4 feb 2026.* door Tekenaar Voorbeeld$/);
  });

  it('gives the delivery of an offer to the client’s own grip', () => {
    const offer = { id: 'o-3', channel: 'client_instance', offered_at: '2026-02-02T10:00:00Z' };
    expect(offerState({ ...offer, delivery: 'pending' }, QUOTE)).toBe('Onderweg naar de opdrachtgever');
    expect(offerState({ ...offer, delivery: 'sent' }, QUOTE)).toBe('Afgeleverd bij de opdrachtgever');
    expect(offerState({ ...offer, delivery: 'refused' }, QUOTE)).toBe(
      'Niet afgeleverd bij de opdrachtgever',
    );
  });

  it('shows one entry per signing link, the latest offer on it', () => {
    const again = link('opened', { id: 'o-9', offered_at: '2026-02-06T10:00:00Z' });
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
