/**
 * Where a potential assignment stands on its way to an agreement.
 *
 * One function decides it, from facts: is there a budget, a quote in force,
 * an offer, an agreement. The step bar, the sentence under it and the
 * primary action all read its answer, so they cannot disagree. A fact that
 * is not known makes the answer say less, never something else.
 */
import { formatDate } from '@/lib/format';
import type { AssignmentTabKey } from './paths';

export interface QuoteFact {
  status: string;
  issued_at: string;
  valid_until?: string | null;
  /**
   * Internal approval, only when this quote needs it: the status the
   * approvals API gives (none, requested, approved, sent_back, withdrawn).
   */
  approval?: string | null;
  /** Why the quote cannot be offered yet, in the server's words. */
  blockedMessage?: string | null;
}

export interface OfferFact {
  channel: string;
  offered_at: string;
  /** State of the signing link: invited, opened, signed, expired, withdrawn. */
  invitationState?: string | null;
}

export interface StandingFacts {
  phase: string;
  status: string;
  /** The reader may work on budget and quote. */
  mayAct: boolean;
  /** "Eva Eigenaar of Pim Planner", for a reader who cannot act. */
  owners: string;
  /** The assignment says a quote was made; used when the quotes are not known. */
  quoteSeen?: boolean;
  /** Number of budget lines; undefined when not known. */
  budgetLines?: number;
  /** All quotes of the assignment; undefined when not known. */
  quotes?: readonly QuoteFact[];
  /** Offers of the quote in force; undefined when not known. */
  offers?: readonly OfferFact[];
  /** First day as yyyy-mm-dd, to tell whether a quote has expired. */
  today: string;
}

export type StepKey = 'budget' | 'quote' | 'approval' | 'offer' | 'agreement';

export interface StandingStep {
  key: StepKey;
  text: string;
  state: 'done' | 'current' | 'future';
  /** The tab where the step is done, for a reader who has it. */
  tab?: AssignmentTabKey;
}

export interface Standing {
  steps: StandingStep[];
  current: StepKey;
  /** One sentence: where it stands and what happens next. */
  advice: string;
  /** The one thing that helps now, for a reader who can do it. */
  action: { text: string; tab: AssignmentTabKey } | null;
}

const STEP_TEXT: Record<StepKey, string> = {
  budget: 'Begroting opstellen',
  quote: 'Offerte maken',
  approval: 'Intern akkoord',
  offer: 'Offerte aanbieden',
  agreement: 'Akkoord van de opdrachtgever',
};

const STEP_TAB: Partial<Record<StepKey, AssignmentTabKey>> = {
  budget: 'budget',
  quote: 'quote',
  approval: 'quote',
  offer: 'quote',
  agreement: 'quote',
};

const CHANNEL_TEXT: Record<string, string> = {
  signing_link: 'met een tekenlink',
  document: 'als document',
  client_instance: 'via het grip van de opdrachtgever',
};

function offerSentence(offer: OfferFact): string {
  const how = CHANNEL_TEXT[offer.channel] ?? '';
  const when = formatDate(offer.offered_at.slice(0, 10));
  const response =
    offer.invitationState === 'opened'
      ? 'geopend, nog niet getekend'
      : offer.invitationState === 'expired'
        ? 'de tekenlink is verlopen'
        : offer.invitationState === 'withdrawn'
          ? 'de tekenlink is ingetrokken'
          : 'nog geen reactie';
  return `Aangeboden ${how ? `${how} ` : ''}op ${when}; ${response}.`;
}

const latest = <T>(items: readonly T[], key: (item: T) => string): T | undefined =>
  [...items].sort((a, b) => key(a).localeCompare(key(b))).at(-1);

/** Where the assignment stands; null once it is no longer potential. */
export function standing(facts: StandingFacts): Standing | null {
  if (facts.phase !== 'potential') return null;
  const act = facts.mayAct;
  const lastQuote = facts.quotes ? latest(facts.quotes, (quote) => quote.issued_at) : undefined;
  const expired =
    lastQuote?.status === 'issued' && !!lastQuote.valid_until && lastQuote.valid_until < facts.today;
  const inForce = lastQuote?.status === 'issued' && !expired ? lastQuote : undefined;
  // Without the list of quotes, the assignment itself still says one was made.
  const quoteMade =
    facts.quotes !== undefined ? inForce !== undefined : facts.status === 'quoted' || !!facts.quoteSeen;
  const lastOffer = inForce && facts.offers ? latest(facts.offers, (o) => o.offered_at) : undefined;
  const withApproval = !!inForce?.approval;

  const keys: StepKey[] = ['budget', 'quote', ...(withApproval ? ['approval' as const] : []), 'offer', 'agreement'];
  const answer = (
    current: StepKey,
    advice: string,
    action: { text: string; tab: AssignmentTabKey } | null,
  ): Standing => {
    const at = keys.indexOf(current);
    return {
      steps: keys.map((key, index) => ({
        key,
        text: STEP_TEXT[key],
        state: index < at ? 'done' : index === at ? 'current' : 'future',
        ...(act && STEP_TAB[key] ? { tab: STEP_TAB[key] } : {}),
      })),
      current,
      advice,
      action: act ? action : null,
    };
  };
  const toQuote = { text: 'Ga naar de offerte', tab: 'quote' as const };

  if (facts.status === 'verbally_agreed') {
    return answer(
      'agreement',
      'De opdrachtgever heeft mondeling akkoord gegeven. Leg het getekende akkoord vast om de opdracht te laten ingaan.',
      { text: 'Leg het getekende akkoord vast', tab: 'quote' },
    );
  }
  if (inForce?.approval === 'sent_back') {
    return answer(
      'quote',
      'De offerte is intern teruggestuurd. Pas de begroting aan en maak een nieuwe offerte.',
      toQuote,
    );
  }
  if (inForce?.approval === 'requested') {
    return answer(
      'approval',
      inForce.blockedMessage ?? 'De offerte wacht op intern akkoord voordat zij naar de opdrachtgever kan.',
      toQuote,
    );
  }
  if (inForce?.approval === 'none' || inForce?.approval === 'withdrawn') {
    return answer(
      'approval',
      inForce.blockedMessage ?? 'Deze offerte heeft intern akkoord nodig voordat zij naar de opdrachtgever kan.',
      { text: 'Vraag intern akkoord', tab: 'quote' },
    );
  }
  if (lastOffer) {
    return answer(
      'agreement',
      offerSentence(lastOffer),
      lastOffer.channel === 'document'
        ? { text: 'Leg het getekende akkoord vast', tab: 'quote' }
        : { text: 'Open de offerte', tab: 'quote' },
    );
  }
  if (quoteMade) {
    // Offers not known: say only what is certain, that a quote exists.
    const known = facts.offers !== undefined;
    return answer(
      'offer',
      known
        ? act
          ? 'De offerte is gemaakt. Bied die aan de opdrachtgever aan.'
          : `De offerte is gemaakt. ${facts.owners} biedt die aan de opdrachtgever aan.`
        : 'De offerte is gemaakt.',
      known ? { text: 'Bied de offerte aan', tab: 'quote' } : toQuote,
    );
  }
  if (expired && lastQuote?.valid_until) {
    return answer(
      'quote',
      `De offerte is verlopen op ${formatDate(lastQuote.valid_until)}. Maak een nieuwe offerte.`,
      { text: 'Maak een nieuwe offerte', tab: 'quote' },
    );
  }
  if (lastQuote?.status === 'rejected') {
    return answer(
      'quote',
      'De opdrachtgever heeft de offerte afgewezen. Maak een nieuwe offerte, of sluit de opdracht af.',
      toQuote,
    );
  }
  if ((facts.budgetLines ?? 0) > 0) {
    return answer(
      'quote',
      act
        ? 'De begroting staat. Maak er een offerte van.'
        : `De begroting staat. ${facts.owners} maakt er een offerte van.`,
      { text: 'Maak de offerte', tab: 'quote' },
    );
  }
  return answer(
    'budget',
    act
      ? 'Dit is nog een potentiële opdracht. Stel de begroting op en maak daar een offerte van.'
      : `Dit is nog een potentiële opdracht. ${facts.owners} maakt eerst de begroting.`,
    { text: 'Maak de begroting', tab: 'budget' },
  );
}
