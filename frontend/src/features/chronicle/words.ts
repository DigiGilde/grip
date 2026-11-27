/** What a moment says in words. Pure, and nothing here decides what may be seen. */
import { ACCEPTANCE_FORM_LABELS } from '@/features/quotes/api';
import { nameSaysRole } from '@/features/quotes/format';
import { endedLinkText, offerTitle, quoteLabel } from '@/features/quotes/offers';
import { actor, formatMoment } from '@/features/history/words';
import { formatDate, formatFte, formatPeriod } from '@/lib/format';
import { ZONE } from '@/lib/today';
import type {
  LaterKnown,
  Moment,
  Restatement,
  StandAcceptance,
  StandApproval,
  StandBudgetLine,
  StandOffer,
  StandQuote,
  StandRejection,
} from './api';

/** A line of what happened, with at most one quiet line under it. */
export interface Told {
  text: string;
  note?: string;
}

const LONG_DAY = new Intl.DateTimeFormat('nl-NL', {
  day: 'numeric',
  month: 'long',
  year: 'numeric',
  timeZone: ZONE,
});

const TIME = new Intl.DateTimeFormat('nl-NL', {
  hour: '2-digit',
  minute: '2-digit',
  timeZone: ZONE,
});

/** "Stand op 3 november 2026, 14:02". Day and time apart: together Intl joins them with "om". */
export function standTitle(occurredAt: string): string {
  const moment = new Date(occurredAt);
  return `Stand op ${LONG_DAY.format(moment)}, ${TIME.format(moment)}`;
}

/** The sentence of a moment, or its title for who may not read the sentence. */
export function momentText(moment: Pick<Moment, 'statement' | 'title'>): string {
  return moment.statement ?? moment.title;
}

/** "3 nov 2026 14:02 · Anna Voorbeeld", or who it was where no name says so: "Gast". */
export function momentByline(moment: Moment): string {
  const who = moment.actor_kind
    ? actor({ actor_name: moment.actor_name, actor_kind: moment.actor_kind })
    : moment.actor_name;
  return [formatMoment(moment.occurred_at), who].filter(Boolean).join(' · ');
}

/** A sentence names its own day; who gets only a title may not know that day. */
export function laterKnownText(later: LaterKnown): string {
  return `Later vastgelegd: ${later.statement ?? later.title}`;
}

const DUTCH_LIST = new Intl.ListFormat('nl', { style: 'long', type: 'conjunction' });

/** Where a text of this moment was taken out later, without saying what it was. */
export function restatedText(restatement: Restatement): string {
  const labels = restatement.removed.map((label) => label.charAt(0).toLowerCase() + label.slice(1));
  return `Later verwijderd: ${DUTCH_LIST.format(labels)}`;
}

/** The quiet line under a budget line: what the reader may see of it, unless its name says it. */
export function budgetLineSummary(line: StandBudgetLine): string {
  const role = line.role ?? '';
  return [
    nameSaysRole(line.description, role) ? '' : role,
    line.fte ? `${formatFte(line.fte)} FTE` : '',
    line.kind === 'fixed' && line.year ? String(line.year) : '',
    formatPeriod(line.start_date, line.end_date),
    line.rate_category ? `Categorie ${line.rate_category}` : '',
  ]
    .filter(Boolean)
    .join(' · ');
}

/**
 * The word for where a quote stood, as its card said it then. The last row is
 * where the approval stands: a withdrawn one leaves the plain word, as on the card.
 */
export function standQuoteLabel(quote: StandQuote): string {
  return quoteLabel(quote.status, quote.offers ?? [], quote.approvals?.at(-1)?.status);
}

export function approvalTold(approval: StandApproval): Told {
  const by = (name: string | null) => (name ? ` door ${name}` : '');
  const when = approval.decided_at ? ` op ${formatMoment(approval.decided_at)}` : '';
  const asked = approval.request_note
    ? `Toelichting bij de aanvraag: ${approval.request_note}`
    : null;
  const words = [approval.decision_note, asked].filter(Boolean).join(' · ');
  const askedItself =
    approval.decided_by_name && approval.requested_by_name === approval.decided_by_name;
  const note = words ? { note: words } : {};
  switch (approval.status) {
    case 'approved':
      return {
        text: `Intern goedgekeurd${when}${by(approval.decided_by_name)}${
          !approval.self_approved
            ? ''
            : askedItself
              ? ', die de goedkeuring zelf vroeg'
              : ', die de offerte ook maakte'
        }`,
        ...note,
      };
    case 'sent_back':
      return { text: `Teruggestuurd${when}${by(approval.decided_by_name)}`, ...note };
    case 'withdrawn':
      return {
        text: `${approval.decided_at ? 'Goedkeuring' : 'Aanvraag'} ingetrokken${
          approval.withdrawn_at ? ` op ${formatMoment(approval.withdrawn_at)}` : ''
        }${by(approval.withdrawn_by_name)}`,
        ...note,
      };
    default:
      return {
        text: `Wacht op goedkeuring sinds ${formatMoment(approval.requested_at)}${
          approval.requested_by_name ? `, gevraagd door ${approval.requested_by_name}` : ''
        }`,
        ...note,
      };
  }
}

export function offerTold(offer: StandOffer): Told {
  const ended = offer.invitation ? endedLinkText(offer.invitation) : null;
  const offered = `Op ${formatMoment(offer.offered_at)}${
    offer.offered_by_name ? ` door ${offer.offered_by_name}` : ''
  }`;
  return {
    text: offerTitle(offer),
    note: ended ? `${offered} · ${ended}` : offered,
  };
}

/** The day only: a typed date is stored at noon, so a time would be false precision. */
export function acceptanceTold(acceptance: StandAcceptance): Told {
  const form = ACCEPTANCE_FORM_LABELS[acceptance.form];
  const recorder = acceptance.recorded_by_name;
  const note = [form, recorder && recorder !== acceptance.signer_name ? `door ${recorder}` : null]
    .filter(Boolean)
    .join(' ');
  return {
    text: `Getekend op ${formatDate(acceptance.signed_at)} door ${acceptance.signer_name}${
      acceptance.organisation_name ? ` namens ${acceptance.organisation_name}` : ''
    }`,
    ...(note ? { note } : {}),
  };
}

export function rejectionTold(rejection: StandRejection): Told {
  return {
    text: `Afgewezen op ${formatDate(rejection.rejected_at)}${
      rejection.reason ? `: ${rejection.reason}` : ''
    }`,
    ...(rejection.recorded_by_name
      ? { note: `Vastgelegd door ${rejection.recorded_by_name}` }
      : {}),
  };
}
