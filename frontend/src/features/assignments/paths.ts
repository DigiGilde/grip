import { PATHS } from '@/paths';

/** The page of one assignment. */
export const assignmentPath = (id: string) => `${PATHS.assignments}/${id}`;
export const assignmentQuotePath = (id: string) => `${assignmentPath(id)}/offerte`;
export const assignmentMonthClosePath = (id: string) => `${assignmentPath(id)}/maandafsluiting`;

/** The tabs of an assignment, each with its own address. */
export const ASSIGNMENT_TAB_SEGMENTS = {
  overview: '',
  tasks: 'taken',
  finance: 'financieel',
  staffing: 'bemensing',
  budget: 'begroting',
  quote: 'offerte',
  monthClose: 'maandafsluiting',
  history: 'geschiedenis',
} as const;

export type AssignmentTabKey = keyof typeof ASSIGNMENT_TAB_SEGMENTS;

export function assignmentTabPath(id: string, tab: AssignmentTabKey): string {
  const segment = ASSIGNMENT_TAB_SEGMENTS[tab];
  return segment ? `${assignmentPath(id)}/${segment}` : assignmentPath(id);
}
