import { assignmentPartPath } from '@/features/assignments/paths';

/** The report of one assignment. */
export const assignmentReportPath = (id: string) => assignmentPartPath(id, 'report');
