/**
 * An event in words. The stream speaks in kinds and fields; a reader gets a
 * sentence: what happened to what, and from what to what when that may be
 * seen. Nothing here decides what may be seen: a hidden field has no values
 * to show.
 */
import { formatDate, formatEuro } from '@/lib/format';
import type { EventChange, HistoryEvent } from './api';

/** A kind of subject: the noun, and whether it takes "de" (true) or "het". */
export const KIND_LABELS: Record<string, string> = {
  assignment: 'Opdracht',
  assignment_request: 'Aanvraag',
  assignment_role: 'Rol op de opdracht',
  task: 'Taak',
  budget_line: 'Begrotingsregel',
  budget_usage_requested: 'Inzage in het budget',
  quote: 'Offerte',
  quote_draft: 'Concept van de offerte',
  quote_offer: 'Aanbieding van de offerte',
  quote_invitation: 'Uitnodiging om te tekenen',
  quote_acceptance: 'Akkoord op de offerte',
  quote_rejection: 'Afwijzing van de offerte',
  quote_approval: 'Interne goedkeuring',
  decision_evidence: 'Bewijs van het besluit',
  final_report: 'Eindrapport',
  final_report_received: 'Ontvangen eindrapport',
  month_close: 'Maandafsluiting',
  billing_export: 'Factuurgegevens',
  billing_correction: 'Correctie op factuurgegevens',
  outgoing_invoice: 'Factuur',
  invoice_line: 'Factuurregel',
  invoice_attachment: 'Bijlage bij de factuur',
  cost_item: 'Kostenpost',
  cost_coverage: 'Dekking van de kosten',
  allocation: 'Inzet',
  person: 'Persoon',
  person_standing: 'Dienstverband',
  person_role: 'Recht in grip',
  person_roles: 'Rollen',
  colleague_proposal: 'Voorstel voor een collega',
  person_scale: 'Schaal',
  hire: 'Inhuur',
  billability_target: 'Norm voor declarabiliteit',
  vacancy: 'Vacature',
  vacancy_text: 'Vacaturetekst',
  vacancy_step: 'Stap van de procedure',
  vacancy_decision: 'Advies of akkoord',
  vacancy_recruitment_ref: 'Verwijzing naar de werving',
  vacancy_offer_received: 'Aangeboden kandidaat',
  vacancy_hire: 'Invulling van de vacature',
  rate_card: 'Tarievenkaart',
  rate_band: 'Tarief',
  scale_band: 'Indeling van een schaal',
  organisation: 'Organisatie',
  organisation_sync: 'Ophalen van organisaties',
  catalogue_role: 'Rol',
  catalogue_role_sync: 'Ophalen van rollen',
  function_framework: 'Functiegebouw',
  function_family: 'Functiefamilie',
  function_group: 'Functiegroep',
  form_template: 'Aanvraagformulier',
  instance_setting: 'Instelling',
  peer: 'Koppeling',
  mail_outbox: 'Uitgaande mail',
  stream: 'Geschiedenis',
  data: 'Gegevens',
};

const VERBS: Record<string, string> = {
  created: 'toegevoegd',
  updated: 'gewijzigd',
  deleted: 'verwijderd',
};

/** Events that are more than a change of fields have a sentence of their own. */
const TYPE_SENTENCES: Record<string, string> = {
  'assignment_request.created': 'Offerte aangevraagd',
  'assignment.status_changed': 'Status van de opdracht gewijzigd',
  'quote.issued': 'Offerte gemaakt',
  'quote.offered': 'Offerte aangeboden',
  'quote.accepted': 'Offerte aanvaard',
  'quote.rejected': 'Offerte afgewezen',
  'quote_approval.requested': 'Interne goedkeuring gevraagd',
  'quote_approval.approved': 'Offerte intern goedgekeurd',
  'quote_approval.sent_back': 'Offerte teruggestuurd naar de maker',
  'quote_approval.withdrawn': 'Vraag om goedkeuring ingetrokken',
  'final_report.issued': 'Eindrapport uitgebracht',
  'vacancy.published': 'Vacature opengesteld',
  'invoice.recorded': 'Factuur vastgelegd',
  'invoice.withdrawn': 'Factuur ingetrokken',
  'person_scale.changed': 'Schaal gewijzigd',
  'billing_correction.arose': 'Correctie op factuurgegevens ontstaan',
  'data.read': 'Gegevens ingezien',
  'stream.erased': 'Waarden uit de geschiedenis gewist',
};

/** The types that say what a group of changes was about. */
const HEADLINE_TYPES = new Set(Object.keys(TYPE_SENTENCES));

const FIELD_LABELS: Record<string, string> = {
  name: 'Naam',
  status: 'Status',
  new_status: 'Status',
  start_date: 'Begindatum',
  end_date: 'Einddatum',
  started_on: 'Begonnen op',
  ended_on: 'Afgerond op',
  valid_from: 'Ingangsdatum',
  valid_to: 'Einddatum',
  billing_scale: 'Schaal',
  scale: 'Schaal',
  fte: 'Fte',
  fte_pct: 'Inzet',
  description: 'Omschrijving',
  role: 'Rol',
  amount_cents: 'Bedrag',
  quoted_amount_cents: 'Offertebedrag',
  total_cents: 'Totaal',
  monthly_rate_cents: 'Maandtarief',
  target: 'Norm',
  reason: 'Reden',
  function_title: 'Functie',
  stage: 'Fase',
  invoice_number: 'Factuurnummer',
  invoice_date: 'Factuurdatum',
};

const ISO_DATE = /^\d{4}-\d{2}-\d{2}/;

function valueText(field: string, value: unknown): string | null {
  if (value === null || value === undefined || value === '') return null;
  if (typeof value === 'boolean') return value ? 'ja' : 'nee';
  if (typeof value === 'number') {
    return field.endsWith('_cents') ? formatEuro(value) : value.toLocaleString('nl-NL');
  }
  if (typeof value === 'string') {
    if (ISO_DATE.test(value)) return formatDate(value) || value;
    return field === 'fte_pct' ? `${value}%` : value;
  }
  return null;
}

/** "Schaal van 11 naar 12", or null when the field has no words. */
function changeText(change: EventChange): string | null {
  const label = FIELD_LABELS[change.field];
  if (!label || !change.visible) return null;
  const before = valueText(change.field, change.old);
  const after = valueText(change.field, change.new);
  if (before && after) return before === after ? null : `${label} van ${before} naar ${after}`;
  if (after) return `${label} ${after}`;
  if (before) return `${label} ${before} vervalt`;
  return null;
}

/** What happened, in one line. Names the person when the reader may know. */
export function headline(event: HistoryEvent): string {
  const sentence = TYPE_SENTENCES[event.type];
  const person = event.person_name;
  if (sentence) {
    if (event.type === 'person_scale.changed' && person) return `Schaal van ${person} gewijzigd`;
    if (event.type === 'data.read' && person) return `Gegevens van ${person} ingezien`;
    return sentence;
  }
  const kind = KIND_LABELS[event.subject_kind] ?? 'Gegevens';
  const verb = VERBS[event.type.split('.')[1] ?? ''] ?? 'gewijzigd';
  return person && event.subject_kind !== 'person'
    ? `${kind} van ${person} ${verb}`
    : person
      ? `${person} ${verb}`
      : `${kind} ${verb}`;
}

/**
 * The change in words, for who may see it: "van 11 naar 12 per 1 juli 2026".
 * Empty for a reader who may only know that it happened.
 */
export function detail(event: HistoryEvent): string {
  if (event.erased) return 'De waarden zijn gewist';
  const from = event.changes.find((change) => change.field === 'valid_from');
  const parts = event.changes
    .filter((change) => change.field !== 'valid_from' || event.subject_kind !== 'person_scale')
    .map(changeText)
    .filter((text): text is string => text !== null);
  if (event.subject_kind === 'person_scale' && from?.visible && parts.length > 0) {
    const when = valueText('valid_from', from.new);
    if (when) parts[parts.length - 1] += ` per ${when}`;
  }
  const payload = event.payload ?? {};
  for (const field of ['new_status', 'reason']) {
    const text = valueText(field, payload[field]);
    if (text) parts.push(`${FIELD_LABELS[field]} ${text}`);
  }
  if (event.note) parts.push(event.note);
  return parts.join(' · ');
}

export function actor(event: HistoryEvent): string {
  if (event.actor_name) return event.actor_name;
  switch (event.actor_kind) {
    case 'guest':
      return 'Gast';
    case 'peer':
      return 'Andere instantie';
    case 'system':
      return 'Systeem';
    default:
      return 'Onbekend';
  }
}

export interface Moment {
  key: string;
  occurred_at: string;
  headline: string;
  /** The other things the same action changed, each in a line. */
  lines: string[];
  actor: string;
}

/**
 * One row per action. What one request changed comes as several events with
 * one correlation id; the reader sees one moment, named after the event that
 * says what it was about, with the rest as lines below it.
 */
export function moments(events: readonly HistoryEvent[]): Moment[] {
  const groups = new Map<string, HistoryEvent[]>();
  for (const event of events) {
    const group = groups.get(event.correlation_id);
    if (group) group.push(event);
    else groups.set(event.correlation_id, [event]);
  }
  return [...groups.entries()].map(([key, group]) => {
    const lead = group.find((event) => HEADLINE_TYPES.has(event.type)) ?? group[group.length - 1]!;
    const lines: string[] = [];
    const own = detail(lead);
    if (own) lines.push(own);
    for (const event of group) {
      if (event === lead) continue;
      const text = headline(event);
      const more = detail(event);
      const line = more ? `${text}: ${more}` : text;
      if (text !== headline(lead) || more) if (!lines.includes(line)) lines.push(line);
    }
    return {
      key,
      occurred_at: lead.occurred_at,
      headline: headline(lead),
      lines,
      actor: actor(lead),
    };
  });
}

const momentFormat = new Intl.DateTimeFormat('nl-NL', {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
});

export function formatMoment(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? '' : momentFormat.format(date);
}
