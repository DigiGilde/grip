/** The way of a vacancy from a role to someone in it, and where it stands. */
import type { Vacancy } from './api';
import { CONTRACT_TYPE_LABELS } from './labels';

/** What the step asks the reader to do, when it is theirs to do. */
export type StepAction = 'prepare' | 'submit' | 'decide' | 'open' | 'fill';

/** The names of the steps: the same words in the step bar and in the list. */
export const STEP_NAMES: Record<StepAction, string> = {
  prepare: 'Aanvraag voorbereiden',
  submit: 'Aanvragen',
  decide: 'Advies en akkoord',
  open: 'Openstellen',
  fill: 'Vervullen',
};

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
