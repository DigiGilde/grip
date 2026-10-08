/** Dutch words for the code lists of a vacancy. */
import { formatDate, formatFte } from '@/lib/format';
import type {
  Channel,
  ContractType,
  TextKind,
  TextVersion,
  VacancyStatus,
  VacancyType,
} from './api';

export const STATUS_LABELS: Record<VacancyStatus, string> = {
  draft: 'Concept',
  requested: 'Aangevraagd',
  approved: 'Akkoord',
  rejected: 'Afgewezen',
  open: 'Opengesteld',
  filled: 'Vervuld',
  withdrawn: 'Ingetrokken',
};

export const STATUS_COLORS: Record<
  VacancyStatus,
  'neutral' | 'accent' | 'success' | 'critical'
> = {
  draft: 'neutral',
  requested: 'accent',
  approved: 'success',
  rejected: 'critical',
  open: 'success',
  filled: 'neutral',
  withdrawn: 'neutral',
};

export const VACANCY_TYPE_LABELS: Record<VacancyType, string> = {
  regulier: 'Regulier',
  specialistisch: 'Specialistisch',
  beoogd: 'Beoogde kandidaat',
  gerede: 'Gerede kandidaat',
};

export const CONTRACT_TYPE_LABELS: Record<ContractType, string> = {
  temporary_project: 'Tijdelijk (projectcontract)',
  temporary_before_permanent: 'Tijdelijk voorafgaand aan vast',
};

export const CHANNEL_LABELS: Record<Channel, string> = {
  internal: 'Intern, binnen de eigen organisatie',
  federated: 'Andere instanties van grip',
  recruitment: 'Werving via recruitment',
};

export const TEXT_KIND_LABELS: Record<TextKind, string> = {
  vacancy_text: 'Vacaturetekst',
  motivation: 'Aanleiding en motivatie',
};

/** "Schaal 11, 0,8 fte": the line under a function title. */
export function scaleAndFte(scale: number | null | undefined, fte: string): string {
  const parts = [];
  if (scale !== null && scale !== undefined) parts.push(`Schaal ${scale}`);
  const amount = formatFte(fte);
  if (amount) parts.push(`${amount} fte`);
  return parts.join(', ');
}

/** Where a version of a text came from, in one sentence. */
export function originOf(version: TextVersion): string {
  if (version.source === 'model') {
    return `Opgesteld door een taalmodel (${version.model_id ?? 'onbekend model'}) op ${formatDate(version.created_at)}`;
  }
  if (version.model_assisted) {
    const drafted = version.origin_drafted_at ? ` van ${formatDate(version.origin_drafted_at)}` : '';
    return `Geschreven door een mens op ${formatDate(version.created_at)}, op basis van een concept van een taalmodel (${version.origin_model_id ?? 'onbekend model'})${drafted}`;
  }
  return `Geschreven door een mens op ${formatDate(version.created_at)}`;
}

/** The same, for the text everyone sees of a published vacancy. */
export function publishedOrigin(text: {
  model_assisted: boolean;
  model_id?: string | null;
  drafted_at?: string | null;
  established_at: string;
}): string {
  const established = `Vastgesteld door een mens op ${formatDate(text.established_at)}.`;
  if (!text.model_assisted) return established;
  const drafted = text.drafted_at ? ` op ${formatDate(text.drafted_at)}` : '';
  return `${established} Een taalmodel (${text.model_id ?? 'onbekend model'}) schreef${drafted} het eerste concept.`;
}
