/**
 * What the pages under one assignment share: the assignment itself, and
 * which tabs its reader gets.
 */
import { createContext, useContext } from 'react';
import type { AssignmentDetail, AssignmentPermissions } from './api';
import type { AssignmentTabKey } from './paths';

export const AssignmentShellContext = createContext<AssignmentDetail | null>(null);

/**
 * The assignment whose tabs surround this page, or null when the page is
 * rendered on its own. A page that can live in both places uses this to
 * leave its own page heading and back link out when the shell provides them.
 */
export function useAssignmentShell(): AssignmentDetail | null {
  return useContext(AssignmentShellContext);
}

export const TAB_LABELS: Record<AssignmentTabKey, string> = {
  overview: 'Overzicht',
  finance: 'Financieel',
  staffing: 'Bemensing',
  budget: 'Begroting',
  quote: 'Offerte',
  monthClose: 'Maandafsluiting',
};

const TAB_ORDER: readonly AssignmentTabKey[] = [
  'overview',
  'finance',
  'staffing',
  'budget',
  'quote',
  'monthClose',
];

/**
 * The tabs this reader gets. A tab that has nothing for the reader is
 * absent, not disabled: money needs the financial class, the team needs at
 * least the roster.
 */
export function visibleTabs(permissions: AssignmentPermissions): AssignmentTabKey[] {
  const money = permissions.read_financial;
  const team = permissions.read_staffing || permissions.read_roster;
  const shown: Record<AssignmentTabKey, boolean> = {
    overview: true,
    finance: money,
    staffing: team,
    budget: money,
    quote: money,
    monthClose: money || permissions.read_staffing,
  };
  return TAB_ORDER.filter((tab) => shown[tab]);
}
