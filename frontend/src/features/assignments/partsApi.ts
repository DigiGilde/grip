/** The rows of an assignment, as the server gives them for this reader. */
import { apiGet } from '@/api/client';
import type { AssignmentPartKey } from './paths';

export interface AssignmentPart {
  key: Exclude<AssignmentPartKey, 'landing' | 'tasks'>;
  label: string;
  /** What is the matter with this part; null when there is nothing to say. */
  notice: string | null;
}

export interface AssignmentParts {
  assignment_id: string;
  parts: AssignmentPart[];
  /** The reader runs the assignment: "Alle taken van deze opdracht" is theirs. */
  tasks_link: boolean;
  /** This instance asked for the assignment: the work of the contractor is not here. */
  is_client: boolean;
  /** The reader's own work on the assignment, in one line. */
  own_line: string | null;
}

export const fetchAssignmentParts = (id: string) =>
  apiGet<AssignmentParts>(`/api/assignments/${id}/parts`);
