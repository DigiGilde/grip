/** Who runs an assignment, in words. Where it stands is decided in standing.ts. */
import type { AssignmentDetail } from './api';

/** "Eva Eigenaar of Pim Planner", the people who run the assignment. */
export function ownersText(assignment: AssignmentDetail): string {
  const names = assignment.roles.map((holder) => holder.name);
  if (names.length === 0) return 'De eigenaar van de opdracht';
  if (names.length === 1) return names[0] ?? '';
  return `${names.slice(0, -1).join(', ')} of ${names[names.length - 1]}`;
}
