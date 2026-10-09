import { createElement, useState } from 'react';
import type { RequestHeaders } from '@/api/client';
import { ConflictPanel } from '@/ui/ConflictPanel';
import { useStaleChoice } from '@/ui/stale';
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
  change: (input: Input, headers?: RequestHeaders) => Promise<Vacancy>,
  onDone?: () => void,
  /**
   * For the save of a sheet: the version of the vacancy as the page holds it
   * now, and what the sheet belongs to (whether it is open). The save then
   * goes out on the version the sheet was opened on, and one that is refused
   * because a colleague changed the vacancy in between ends in `panel`.
   */
  record?: { version: number | undefined; restart?: unknown },
) {
  const queryClient = useQueryClient();
  const stale = useStaleChoice(
    record ? vacancyId : null,
    record?.version,
    () => queryClient.invalidateQueries({ queryKey: VACANCY_KEYS.detail(vacancyId) }),
    record?.restart ?? null,
  );
  const [failure, setFailure] = useState<string | null>(null);
  const mutation = useMutation({
    mutationFn: ({ input, onTop }: { input: Input; onTop: boolean }) =>
      change(input, onTop ? stale.latestHeaders : stale.headers),
    onMutate: () => setFailure(null),
    onError: async (error) => {
      if (!(await stale.caught(error))) setFailure(errorMessage(error));
    },
    onSuccess: (vacancy) => {
      stale.saved(vacancy.version);
      queryClient.setQueryData(VACANCY_KEYS.detail(vacancyId), vacancy);
      void queryClient.invalidateQueries({ queryKey: VACANCY_KEYS.list });
      void queryClient.invalidateQueries({ queryKey: VACANCY_KEYS.openRoles });
      void queryClient.invalidateQueries({ queryKey: VACANCY_KEYS.unfilledRoles });
      void queryClient.invalidateQueries({ queryKey: VACANCY_KEYS.formStatus(vacancyId) });
      onDone?.();
    },
  });
  return {
    run: (input: Input) => mutation.mutate({ input, onTop: false }),
    busy: mutation.isPending,
    error: failure,
    reset: () => {
      setFailure(null);
      stale.clear();
      mutation.reset();
    },
    /** Who changed the vacancy in between, with the two ways on; null when nobody did. */
    panel: stale.conflict
      ? createElement(ConflictPanel, {
          conflict: stale.conflict,
          busy: mutation.isPending,
          onKeepMine: () => {
            const sent = mutation.variables;
            if (sent) mutation.mutate({ input: sent.input, onTop: true });
          },
          onTakeTheirs: () => {
            stale.clear();
            onDone?.();
          },
        })
      : null,
  };
}

/** Today as an ISO date, in local time. */
export { todayIso } from '@/lib/today';

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
