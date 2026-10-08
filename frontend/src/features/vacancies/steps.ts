/** The way of a vacancy from a role to someone in it, and where it stands. */
import { formatFte } from '@/lib/format';
import type { Vacancy } from './api';
import { CONTRACT_TYPE_LABELS } from './labels';

/** What the step asks the reader to do, when it is theirs to do. */
export type StepAction = 'prepare' | 'submit' | 'decide' | 'open' | 'fill';

export interface VacancySteps {
  items: string[];
  /** 1-based number of the step the vacancy is at. */
  current: number;
  /** One sentence saying what happens now. */
  advice: string;
  action: StepAction | null;
}

/** The names of the steps: the same words in the step bar and in the list. */
export const STEP_NAMES: Record<StepAction, string> = {
  prepare: 'Aanvraag voorbereiden',
  submit: 'Aanvragen',
  decide: 'Advies en akkoord',
  open: 'Openstellen',
  fill: 'Vervullen',
};

/** Where on the page a step is done. */
export const STEP_ANCHORS = {
  decide: 'advies-en-akkoord',
  open: 'procedure',
  fill: 'afronden',
  texts: 'teksten',
} as const;

export interface RequestItem {
  key: 'function_group' | 'scale' | 'contract_type' | 'addressee' | 'motivation';
  label: string;
  /** The value as it will be printed, or null while it is not filled in. */
  value: string | null;
  /** Filled in the request sheet, or (the motivation) under the texts. */
  where: 'sheet' | 'texts';
  /** What to say instead of "not filled in" when something is there but does not count yet. */
  missingText?: string;
}

/** What the request form asks for beyond the role, filled in or not. */
export function requestItems(vacancy: Vacancy): RequestItem[] {
  const motivation = vacancy.texts.find((text) => text.kind === 'motivation' && text.is_current);
  const draft = vacancy.texts.some((text) => text.kind === 'motivation');
  return [
    {
      key: 'function_group',
      label: 'FGR-functienaam',
      value: vacancy.fgr_function_name || null,
      where: 'sheet',
    },
    {
      key: 'scale',
      label: 'Schaal',
      value: vacancy.scale === null || vacancy.scale === undefined ? null : String(vacancy.scale),
      where: 'sheet',
    },
    {
      key: 'contract_type',
      label: 'Type contract',
      value: vacancy.contract_type ? CONTRACT_TYPE_LABELS[vacancy.contract_type] : null,
      where: 'sheet',
    },
    {
      key: 'addressee',
      label: 'Aan',
      value: vacancy.addressee_name || null,
      where: 'sheet',
    },
    {
      key: 'motivation',
      label: 'Aanleiding en motivatie',
      // Printed on the form, so the request waits for a settled one.
      value: motivation ? 'Vastgesteld' : null,
      where: 'texts',
      ...(draft && !motivation ? { missingText: 'Concept, nog vaststellen' } : {}),
    },
  ];
}

/**
 * True when everything the request needs is there. The server keeps the list
 * (`request_missing`) and refuses the request by it; without that list (an
 * older answer) the items on screen decide.
 */
export function requestPrepared(vacancy: Vacancy): boolean {
  if (vacancy.request_missing) return vacancy.request_missing.length === 0;
  return requestItems(vacancy).every((item) => item.value !== null);
}

/** The steps for this type of vacancy and where it stands; null once it has ended. */
export function vacancySteps(vacancy: Vacancy): VacancySteps | null {
  const opens = vacancy.has_openings !== false;
  const items = [
    STEP_NAMES.prepare,
    STEP_NAMES.submit,
    STEP_NAMES.decide,
    ...(opens ? [STEP_NAMES.open] : []),
    STEP_NAMES.fill,
  ];
  const can = vacancy.permissions;
  const fillStep = items.length;
  const fte = formatFte(vacancy.fte);

  switch (vacancy.status) {
    case 'draft':
      if (!requestPrepared(vacancy)) {
        return {
          items,
          current: 1,
          advice: vacancy.request_missing?.length
            ? `Ontbreekt nog: ${vacancy.request_missing.join(', ')}.`
            : 'Vul in wat het aanvraagformulier vraagt: de functienaam uit het Functiegebouw Rijk, de schaal, het type contract, aan wie de aanvraag gericht is en de aanleiding en motivatie.',
          action: can.can_edit ? 'prepare' : null,
        };
      }
      return {
        items,
        current: 2,
        advice: `De aanvraag voor ${fte} fte is voorbereid. Vraag de vacature aan om advies en akkoord te krijgen.`,
        action: can.can_edit ? 'submit' : null,
      };
    case 'requested':
      return {
        items,
        current: 3,
        advice:
          'De vacature is aangevraagd. HR en concern control adviseren, daarna volgt het akkoord.',
        action:
          can.can_edit ||
          can.can_record_hr_advice ||
          can.can_record_control_advice ||
          can.can_record_approval
            ? 'decide'
            : null,
      };
    case 'approved':
      return opens
        ? {
            items,
            current: 4,
            advice:
              'Het akkoord is gegeven. Stel de vacaturetekst vast en stel de vacature open.',
            action: can.can_edit ? 'open' : null,
          }
        : {
            items,
            current: fillStep,
            advice:
              'Het akkoord is gegeven. Een vacature voor een beoogde of gerede kandidaat wordt niet opengesteld; leg vast dat ze is vervuld.',
            action: can.can_fill ? 'fill' : null,
          };
    case 'open':
      return {
        items,
        current: fillStep,
        advice: 'De vacature staat open. Leg vast wanneer ze is vervuld.',
        action: can.can_fill ? 'fill' : null,
      };
    default:
      return null;
  }
}
