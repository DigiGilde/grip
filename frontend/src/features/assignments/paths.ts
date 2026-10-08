import { PATHS } from '@/paths';

/** The page of one assignment. */
export const assignmentPath = (id: string) => `${PATHS.assignments}/${id}`;
export const assignmentQuotePath = (id: string) => `${assignmentPath(id)}/offerte`;
export const assignmentMonthClosePath = (id: string) => `${assignmentPath(id)}/maandafsluiting`;
