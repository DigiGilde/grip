/**
 * The proof of a decision. A decision that matters is not sent to the server
 * directly: the browser asks for an intent, leaves for the identity provider,
 * and comes back with the id of the evidence or with an error code. Until it
 * is back, nothing was decided.
 */
import { useSearchParams } from 'react-router-dom';
import { apiGet, apiPost } from '@/api/client';
import { formatEuro } from '@/lib/format';
import type { Fact } from '@/ui/layout';
import { formatDateTime } from './format';
import { PATHS } from '@/paths';

export interface DecisionIntent {
  id: string;
  /** Where the browser goes, as a full page load. Not an address to fetch. */
  authorize_url: string;
  expires_at: string;
  /** False where no identity provider is set up: nobody vouches for who decides. */
  reauthentication: boolean;
}

export type DecisionKind = 'accept_received' | 'reject_received' | 'approve' | 'send_back';

/** Under which prefix the evidence is read: by who signed, or by who may read the quote. */
export type ProofScope = 'signing' | 'proof';

/** The statement of a decision, in the terms of the contract. */
export interface DecisionStatement {
  besluit?: string;
  offerte?: {
    kenmerk?: string | null;
    totaal_centen?: number | null;
    bestand_sha256?: string | null;
  };
  wie?: { naam?: string | null; functie?: string | null; email?: string | null };
  /** On whose behalf: an organisation as the contract names it, or just a name. */
  namens?: string | { name?: string | null; naam?: string | null } | null;
  wanneer?: { ontvangen_op?: string | null; aangemeld_op?: string | null };
  hoe?: { aanmelding?: { ontbreekt_omdat?: string | null } };
  toelichting?: string | null;
}

export interface Evidence {
  id: string;
  /** accept, reject, approve or send_back. */
  decision: string;
  channel: string;
  quote_id: string;
  statement: DecisionStatement;
  sound: boolean;
  /** Sentences of the server: what the bundle shows, leaves open, contradicts. */
  proven: string[];
  not_proven: string[];
  wrong: string[];
  has_identity_statement: boolean;
  has_timestamp: boolean;
}

export interface QuoteEvidenceRow {
  id: string;
  decision: string;
  channel: string;
  created_at: string;
  has_identity_statement: boolean;
}

export interface VerifyReport {
  sound: boolean;
  proven: string[];
  not_proven: string[];
  wrong: string[];
  statement?: DecisionStatement | null;
}

export const RESULT_PARAM = 'bewijs';
export const ERROR_PARAM = 'besluit_fout';

export const proofKeys = {
  evidence: (scope: ProofScope, id: string) => ['quotes', 'evidence', scope, id] as const,
  ofQuote: (quoteId: string) => ['quotes', 'evidence-of', quoteId] as const,
};

export function createSigningIntent(
  quoteId: string,
  input: {
    decision: 'accept' | 'reject';
    quote_hash: string;
    signer_function?: string | null;
    confirm_mandate?: boolean;
    organisation_name?: string | null;
    reason?: string | null;
    return_path: string;
  },
): Promise<DecisionIntent> {
  return apiPost(`/api/signing/quotes/${quoteId}/intents`, input);
}

export function createDecisionIntent(input: {
  kind: DecisionKind;
  quote_id: string;
  quote_hash: string;
  signer_function?: string | null;
  note?: string | null;
  return_path: string;
}): Promise<DecisionIntent> {
  return apiPost('/api/proof/intents', input);
}

export function fetchEvidence(scope: ProofScope, id: string): Promise<Evidence> {
  return apiGet(`/api/${scope}/evidence/${id}`);
}

export function fetchQuoteEvidence(quoteId: string): Promise<{ items: QuoteEvidenceRow[] }> {
  return apiGet(`/api/proof/quotes/${quoteId}/evidence`);
}

export function bundleUrl(scope: ProofScope, id: string): string {
  return `/api/${scope}/evidence/${id}/bundle`;
}

export function statementPageUrl(scope: ProofScope, id: string): string {
  return `/api/${scope}/evidence/${id}/page`;
}

export function verifyBundle(bundle: unknown): Promise<VerifyReport> {
  // Under the signing prefix, so an invited signer without an account can check too.
  return apiPost('/api/signing/verify', { bundle });
}

/**
 * Leaving the application for the identity provider, or for a file. One
 * object, so a test can see where the browser would have gone.
 */
export const navigation = {
  go(url: string): void {
    window.location.assign(url);
  },
};

// --- what the person filled in, across the round trip ------------------------

const DRAFT_PREFIX = 'grip.besluit.';

/**
 * The server keeps what was filled in with the intent, so a decision that
 * goes through needs nothing from the browser. This copy is for the other
 * outcome: when the browser comes back with an error, the form opens with
 * what the person wrote. It lives in the session of this tab only.
 */
export function saveDraft(quoteId: string, draft: Record<string, unknown>): void {
  try {
    sessionStorage.setItem(DRAFT_PREFIX + quoteId, JSON.stringify(draft));
  } catch {
    // Without storage the person types it again; the decision is unaffected.
  }
}

export function readDraft<T extends Record<string, unknown>>(quoteId: string): T | null {
  try {
    const raw = sessionStorage.getItem(DRAFT_PREFIX + quoteId);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

export function clearDraft(quoteId: string): void {
  try {
    sessionStorage.removeItem(DRAFT_PREFIX + quoteId);
  } catch {
    // Nothing to clear.
  }
}

// --- words --------------------------------------------------------------------

/** What is said before the browser leaves, per decision. */
export function beforeLeaving(decision: 'accept' | 'reject' | 'approve' | 'send_back'): string {
  const after = {
    accept: 'Daarna is je akkoord vastgelegd.',
    reject: 'Daarna is je afwijzing vastgelegd.',
    approve: 'Daarna is je goedkeuring vastgelegd.',
    send_back: 'Daarna is de offerte teruggestuurd.',
  }[decision];
  return `Om te bevestigen dat jij dit bent, log je opnieuw in. ${after}`;
}

export const DECISION_DONE: Record<string, string> = {
  accept: 'Je akkoord is vastgelegd',
  reject: 'Je afwijzing is vastgelegd',
  approve: 'Je goedkeuring is vastgelegd',
  send_back: 'De offerte is teruggestuurd',
};

export const DECISION_WORDS: Record<string, string> = {
  accept: 'Akkoord',
  reject: 'Afgewezen',
  approve: 'Intern goedgekeurd',
  send_back: 'Teruggestuurd',
};

const ERROR_TEXTS: Record<string, string> = {
  verlopen: 'Het duurde te lang tussen je keuze en het inloggen.',
  al_gebruikt: 'Deze bevestiging was al gebruikt.',
  offerte_gewijzigd: 'De offerte is veranderd of vervangen terwijl je bezig was.',
  token_ongeldig: 'Het antwoord van de inlogdienst kon niet worden gecontroleerd.',
  andere_persoon: 'Je logde in als iemand anders dan wie het besluit begon.',
  aanmelding_niet_vers: 'Je bent niet opnieuw ingelogd, en dat is hier wel nodig.',
  aanmelding_mislukt: 'Het inloggen is niet gelukt.',
  geen_aanmelding: 'De inlogdienst gaf geen bevestiging van wie je bent.',
  geen_recht: 'Je mag dit besluit niet nemen.',
  geweigerd: 'Je hebt het inloggen afgebroken.',
  geen_sleutel: 'Het besluit kon niet worden ondertekend door deze omgeving.',
  provider_onbereikbaar: 'De inlogdienst was niet bereikbaar.',
  niet_ingelogd: 'Je was niet meer ingelogd.',
};

/** What went wrong, in plain words; an unknown code still says that it failed. */
export function decisionErrorText(code: string): string {
  return ERROR_TEXTS[code] ?? 'Het besluit kon niet worden vastgelegd.';
}

/** Whether trying again can help, or the reader has to do something else first. */
export function canRetry(code: string): boolean {
  return code !== 'geen_recht' && code !== 'offerte_gewijzigd';
}

export const VERIFY_PATH = PATHS.verifyProof;

/** What the browser came back with after the identity provider. */
export function useDecisionReturn() {
  const [params, setParams] = useSearchParams();
  const evidenceId = params.get(RESULT_PARAM);
  const errorCode = params.get(ERROR_PARAM);
  /** Takes the outcome out of the address, so a reload does not show it again. */
  const dismiss = () => {
    const next = new URLSearchParams(params);
    next.delete(RESULT_PARAM);
    next.delete(ERROR_PARAM);
    setParams(next, { replace: true });
  };
  return { evidenceId, errorCode, dismiss };
}

/** What was decided, on what, by whom and when: the facts of a receipt. */
export function receiptFacts(evidence: Pick<Evidence, 'decision' | 'statement'>): Fact[] {
  const statement = evidence.statement;
  const quote = statement.offerte;
  const who = [statement.wie?.naam, statement.wie?.functie ? `(${statement.wie.functie})` : null]
    .filter(Boolean)
    .join(' ');
  const facts: Fact[] = [
    { label: 'Besluit', value: DECISION_WORDS[evidence.decision] ?? evidence.decision },
    {
      label: 'Offerte',
      value: [
        quote?.kenmerk,
        typeof quote?.totaal_centen === 'number' ? formatEuro(quote.totaal_centen) : null,
      ]
        .filter(Boolean)
        .join(' · '),
    },
    { label: 'Door', value: who },
  ];
  const behalf =
    typeof statement.namens === 'string'
      ? statement.namens
      : (statement.namens?.name ?? statement.namens?.naam ?? null);
  if (behalf) facts.push({ label: 'Namens', value: behalf });
  facts.push({ label: 'Wanneer', value: formatDateTime(statement.wanneer?.ontvangen_op) });
  if (statement.toelichting) facts.push({ label: 'Toelichting', value: statement.toelichting });
  return facts;
}

/** The two moments of a decision, said as they are: no judgement on the gap. */
export function momentsLine(statement: DecisionStatement | null | undefined): string | null {
  const loggedIn = formatDateTime(statement?.wanneer?.aangemeld_op);
  const decided = formatDateTime(statement?.wanneer?.ontvangen_op);
  if (!loggedIn || !decided) return null;
  const done =
    {
      akkoord: 'Akkoord gegeven',
      afwijzing: 'Afgewezen',
      goedkeuring: 'Goedgekeurd',
      teruggestuurd: 'Teruggestuurd',
    }[statement?.besluit ?? ''] ?? 'Besloten';
  return `Ingelogd op ${loggedIn}. ${done} op ${decided}.`;
}
