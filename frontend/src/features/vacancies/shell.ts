/**
 * What the pages under one vacancy share: the vacancy itself, the value
 * lists, its parts for this reader, where it stands, and the sheets that the
 * head and a part can both open.
 */
import { createContext, useContext } from 'react';
import type { Course } from '@/ui/course';
import type { Vacancy, VacancyOptions } from './api';
import type { VacancyPart } from './partsApi';

/** The sheets the layout owns, because the head and a part both open them. */
export type SharedSheet = 'edit' | 'prepare' | 'submit' | 'publish' | 'hire';

/** The one next step of this reader on the page they are on. */
export interface VacancyStep {
  text: string;
  /** Done in this sheet; otherwise at `href`. */
  sheet: SharedSheet | null;
  href: string;
}

export interface VacancyShell {
  vacancy: Vacancy;
  options: VacancyOptions | undefined;
  instanceName: string | undefined;
  openSheet: (sheet: SharedSheet) => void;
  /** The parts the server gives this reader, in their fixed order. */
  parts: readonly VacancyPart[];
  /** Whether the vacancy has tasks this reader may read. */
  tasksLink: boolean;
  course: Course | null | undefined;
  step: VacancyStep | null;
  /**
   * Whether the head of this page holds its one primary button. A part gives
   * its own next step the accent only when it does not.
   */
  headerPrimary: boolean;
  /**
   * The kind of work that is the reader's next step, when it is her move.
   * The part where that step is done gives its button the accent.
   */
  nextTask: string | null;
}

export const VacancyShellContext = createContext<VacancyShell | null>(null);

export function useVacancyShell(): VacancyShell {
  const shell = useContext(VacancyShellContext);
  if (!shell) throw new Error('A part of a vacancy must be rendered inside VacancyLayout.');
  return shell;
}

/** True when the reader gets more than the published text of the vacancy. */
export function seesWholeVacancy(vacancy: Vacancy): boolean {
  return vacancy.vacancy_type !== undefined;
}
