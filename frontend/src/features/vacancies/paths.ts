import { PATHS } from '@/paths';

/** The page of one vacancy. */
export const vacancyPath = (id: string) => `${PATHS.vacancies}/${id}`;

/** The parts of a vacancy, each with its own address. */
export const VACANCY_PART_SEGMENTS = {
  landing: '',
  request: 'aanvraag',
  decisions: 'advies',
  text: 'tekst',
  fulfilment: 'vervulling',
  details: 'gegevens',
  history: 'geschiedenis',
  tasks: 'taken',
} as const;

export type VacancyPartKey = keyof typeof VACANCY_PART_SEGMENTS;

export function vacancyPartPath(id: string, key: VacancyPartKey): string {
  const segment = VACANCY_PART_SEGMENTS[key];
  return segment ? `${vacancyPath(id)}/${segment}` : vacancyPath(id);
}

/** The part of this vacancy an address is on; null for any other address. */
export function vacancyPartAt(id: string, address: string): VacancyPartKey | null {
  const path = (address.split(/[?#]/)[0] ?? '').replace(/\/$/, '');
  const keys = Object.keys(VACANCY_PART_SEGMENTS) as VacancyPartKey[];
  return keys.find((key) => vacancyPartPath(id, key) === path) ?? null;
}

/** The page of a person. */
export const personPath = (id: string) => PATHS.person.replace(':personId', id);

/** The page on which the vacancy text is written. */
export const vacancyTextWritePath = (id: string) =>
  PATHS.vacancyTextWrite.replace(':vacancyId', id);
