import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { errorMessage } from '@/api/client';
import { VACANCY_KEYS, fetchVacancyOptions, type Vacancy } from './api';

/** Value lists and what is set up; they change rarely. */
export function useVacancyOptions() {
  return useQuery({
    queryKey: VACANCY_KEYS.options,
    queryFn: fetchVacancyOptions,
    staleTime: 60_000,
  });
}

/**
 * A change to one vacancy. Every such call answers with the vacancy as the
 * viewer may now see it, which goes straight into the cache; the lists are
 * fetched again.
 */
export function useVacancyChange<Input>(
  vacancyId: string,
  change: (input: Input) => Promise<Vacancy>,
  onDone?: () => void,
) {
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: change,
    onSuccess: (vacancy) => {
      queryClient.setQueryData(VACANCY_KEYS.detail(vacancyId), vacancy);
      void queryClient.invalidateQueries({ queryKey: VACANCY_KEYS.list });
      void queryClient.invalidateQueries({ queryKey: VACANCY_KEYS.openRoles });
      void queryClient.invalidateQueries({ queryKey: VACANCY_KEYS.unfilledRoles });
      void queryClient.invalidateQueries({ queryKey: VACANCY_KEYS.formStatus(vacancyId) });
      onDone?.();
    },
  });
  return {
    run: mutation.mutate,
    busy: mutation.isPending,
    error: mutation.isError ? errorMessage(mutation.error) : null,
    reset: mutation.reset,
  };
}

/** Today as an ISO date, in local time. */
export function todayIso(): string {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  return `${now.getFullYear()}-${month}-${day}`;
}

/** "0,8" or "0.8" as the decimal string the API takes; null when it is not a number. */
export function parseFte(input: string): string | null {
  const normalized = input.trim().replace(',', '.');
  if (!/^\d+(\.\d{1,2})?$/.test(normalized)) return null;
  return Number(normalized) > 0 ? normalized : null;
}

/** A whole scale number, or null for an empty field; undefined when invalid. */
export function parseScale(input: string): number | null | undefined {
  const trimmed = input.trim();
  if (trimmed === '') return null;
  if (!/^\d{1,2}$/.test(trimmed)) return undefined;
  const scale = Number(trimmed);
  return scale >= 1 && scale <= 19 ? scale : undefined;
}
