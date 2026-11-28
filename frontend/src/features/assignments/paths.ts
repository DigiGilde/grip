import { PATHS } from '@/paths';

/** The page of one assignment. */
export const assignmentPath = (id: string) => `${PATHS.assignments}/${id}`;

/** The parts of an assignment, each with its own address. */
export const ASSIGNMENT_PART_SEGMENTS = {
  landing: '',
  close: 'afsluiten',
  budget: 'begroting',
  quote: 'offerte',
  team: 'team',
  report: 'rapport',
  details: 'gegevens',
  history: 'geschiedenis',
  tasks: 'taken',
} as const;

export type AssignmentPartKey = keyof typeof ASSIGNMENT_PART_SEGMENTS;

export function assignmentPartPath(id: string, key: AssignmentPartKey): string {
  const segment = ASSIGNMENT_PART_SEGMENTS[key];
  return segment ? `${assignmentPath(id)}/${segment}` : assignmentPath(id);
}
