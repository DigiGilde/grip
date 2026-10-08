/**
 * Two tasks that read the same must still be told apart. That happens when
 * one assignment has two vacancies for the same function: "Schrijf de
 * motivatie, Vacature Developer" twice. Only then the list asks where each
 * vacancy stands and adds that word to the line under the task.
 */
import { useQuery } from '@tanstack/react-query';
import { VACANCY_KEYS, fetchVacancies } from '@/features/vacancies/api';
import { STATUS_LABELS } from '@/features/vacancies/labels';
import type { Task } from './api';
import { aboutLine, headlineOf } from './telling';

/** The vacancies behind tasks that have the same name and the same subject line. */
export function ambiguousVacancies(tasks: readonly Task[]): Set<string> {
  const byLine = new Map<string, Set<string>>();
  for (const task of tasks) {
    if (!task.vacancy_id) continue;
    const line = `${headlineOf(task)}|${aboutLine(task)}`;
    const ids = byLine.get(line) ?? new Set<string>();
    ids.add(task.vacancy_id);
    byLine.set(line, ids);
  }
  const ambiguous = new Set<string>();
  for (const ids of byLine.values()) {
    if (ids.size > 1) ids.forEach((id) => ambiguous.add(id));
  }
  return ambiguous;
}

/** For each task that needs it, the word that tells its vacancy from its namesake. */
export function useTellApart(tasks: readonly Task[]): (task: Task) => string | undefined {
  const ambiguous = ambiguousVacancies(tasks);
  const vacancies = useQuery({
    queryKey: VACANCY_KEYS.list,
    queryFn: fetchVacancies,
    enabled: ambiguous.size > 0,
  });
  return (task) => {
    if (!task.vacancy_id || !ambiguous.has(task.vacancy_id)) return undefined;
    const vacancy = vacancies.data?.find((item) => item.id === task.vacancy_id);
    return vacancy ? STATUS_LABELS[vacancy.status].toLowerCase() : undefined;
  };
}
