import { PATHS } from '@/paths';

/** The page of one vacancy. */
export const vacancyPath = (id: string) => `${PATHS.vacancies}/${id}`;

/** The tabs of a vacancy, each with its own address. */
export const VACANCY_TAB_SEGMENTS = {
  request: '',
  decisions: 'advies',
  text: 'tekst',
  procedure: 'procedure',
  fulfilment: 'vervulling',
} as const;

export type VacancyTabKey = keyof typeof VACANCY_TAB_SEGMENTS;

export function vacancyTabPath(id: string, tab: VacancyTabKey): string {
  const segment = VACANCY_TAB_SEGMENTS[tab];
  return segment ? `${vacancyPath(id)}/${segment}` : vacancyPath(id);
}

/** The page of a person in the team. */
export const personPath = (id: string) => PATHS.teamPerson.replace(':personId', id);
