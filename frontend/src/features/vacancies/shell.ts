/**
 * What the pages under one vacancy share: the vacancy itself, the value
 * lists, which tabs its reader gets, and the sheets that the header and a
 * tab can both open.
 */
import { createContext, useContext } from 'react';
import type { Vacancy, VacancyOptions } from './api';
import type { VacancyTabKey } from './paths';

/** The sheets the layout owns, because the step bar and a tab both open them. */
export type SharedSheet = 'edit' | 'prepare' | 'submit' | 'publish' | 'hire';

export interface VacancyShell {
  vacancy: Vacancy;
  options: VacancyOptions | undefined;
  openSheet: (sheet: SharedSheet) => void;
}

export const VacancyShellContext = createContext<VacancyShell | null>(null);

export function useVacancyShell(): VacancyShell {
  const shell = useContext(VacancyShellContext);
  if (!shell) throw new Error('A vacancy tab must be rendered inside VacancyLayout.');
  return shell;
}

export const TAB_LABELS: Record<VacancyTabKey, string> = {
  request: 'Aanvraag',
  decisions: 'Advies en akkoord',
  text: 'Tekst',
  procedure: 'Procedure',
  fulfilment: 'Vervulling',
};

const TAB_ORDER: readonly VacancyTabKey[] = [
  'request',
  'decisions',
  'text',
  'procedure',
  'fulfilment',
];

/** True when the reader gets more than the published text of the vacancy. */
export function seesWholeVacancy(vacancy: Vacancy): boolean {
  return vacancy.vacancy_type !== undefined;
}

/**
 * The tabs this reader gets. A tab that has nothing for the reader is
 * absent, not disabled: who only sees the published vacancy gets none, and
 * the recruitment reference and the hire are for who may edit the vacancy.
 */
export function visibleTabs(vacancy: Vacancy): VacancyTabKey[] {
  if (!seesWholeVacancy(vacancy)) return [];
  const shown: Record<VacancyTabKey, boolean> = {
    request: true,
    decisions: true,
    text: true,
    procedure: true,
    fulfilment: vacancy.permissions.can_edit,
  };
  return TAB_ORDER.filter((tab) => shown[tab]);
}

/** The tab on which each step of the vacancy is done. */
export const STEP_TABS = {
  prepare: 'request',
  submit: 'request',
  decide: 'decisions',
  open: 'procedure',
  fill: 'fulfilment',
} as const satisfies Record<string, VacancyTabKey>;
