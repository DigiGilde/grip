/** The parts of one vacancy and where each one stands, as the server decides them. */
import { apiGet } from '@/api/client';

export interface VacancyPart {
  key: 'request' | 'decisions' | 'text' | 'fulfilment' | 'details' | 'history';
  label: string;
  notice: string | null;
  state: 'done' | 'current' | 'waiting' | 'future' | null;
}

export interface VacancyParts {
  vacancy_id: string;
  parts: VacancyPart[];
  tasks_link: boolean;
}

/** Under `course`: a part stands where the course stands, so it is read again with it. */
export const vacancyPartsKey = (id: string) => ['course', 'vacancy', 'parts', id] as const;

export const fetchVacancyParts = (id: string) =>
  apiGet<VacancyParts>(`/api/vacancies/${id}/parts`);
