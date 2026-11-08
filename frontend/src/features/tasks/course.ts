/** Where a case stands, read from the server: the same facts as its tasks. */
import { useEffect } from 'react';
import { keepPreviousData, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiGet } from '@/api/client';
import { courseLine, type Course } from '@/ui/course';

export type CaseKind = 'assignment' | 'vacancy';

export interface CaseCourse {
  case_kind: CaseKind;
  case_id: string;
  /** The course of the case itself; absent for a case without one. */
  course?: Course | null;
  /** The courses of its parts: a text, a billing period. */
  parts?: Course[];
}

export const COURSE_KEYS = {
  one: (kind: CaseKind, id: string) => ['course', kind, id] as const,
  many: (kind: CaseKind, ids: readonly string[]) => ['course', kind, 'list', ...ids] as const,
};

export function fetchCaseCourse(kind: CaseKind, id: string): Promise<CaseCourse> {
  return apiGet<CaseCourse>(`/api/tasks/cases/${kind}/${id}/course`);
}

export async function fetchCourses(kind: CaseKind, ids: readonly string[]): Promise<CaseCourse[]> {
  if (ids.length === 0) return [];
  const found = await apiGet<{ items: CaseCourse[] }>(
    `/api/tasks/courses?case_kind=${kind}&ids=${ids.join(',')}`,
  );
  return found.items;
}

/**
 * Any change made in this window can move a case along: after every save
 * that succeeds, the courses on screen are read again. One rule here, so no
 * screen has to remember to say that it changed something.
 */
function useFreshAfterChanges() {
  const queryClient = useQueryClient();
  useEffect(
    () =>
      queryClient.getMutationCache().subscribe((event) => {
        if (event.type === 'updated' && event.mutation.state.status === 'success') {
          void queryClient.invalidateQueries({ queryKey: ['course'] });
        }
      }),
    [queryClient],
  );
}

/** The course of one case, read again after every change and on return to the window. */
export function useCaseCourse(kind: CaseKind, id: string, enabled = true) {
  useFreshAfterChanges();
  return useQuery({
    queryKey: COURSE_KEYS.one(kind, id),
    queryFn: () => fetchCaseCourse(kind, id),
    enabled: enabled && id !== '',
    retry: false,
    staleTime: 0,
    placeholderData: keepPreviousData,
  });
}

/**
 * Where a case stands and whose move it is, as one sentence for a row. Empty
 * until the course is known. A reader who only looks on is not told whose
 * move it is: it is not theirs to wait for.
 */
export function standingText(course: Course | null | undefined): string {
  const line = courseLine(course);
  if (!line) return '';
  // "Jij: ..." already names the step; for someone else's move the step comes first.
  if (line.mine) return line.who;
  const watching = course?.next?.part === 'watches';
  return [line.step, watching ? '' : line.who].filter(Boolean).join('. ');
}

/** The courses of the cases in a list, by case id. */
export function useCourses(kind: CaseKind, ids: readonly string[]) {
  const sorted = [...ids].sort();
  useFreshAfterChanges();
  const query = useQuery({
    queryKey: COURSE_KEYS.many(kind, sorted),
    queryFn: () => fetchCourses(kind, sorted),
    enabled: sorted.length > 0,
    retry: false,
    staleTime: 0,
    placeholderData: keepPreviousData,
  });
  const byId = new Map((query.data ?? []).map((item) => [item.case_id, item] as const));
  return { byId, isPending: query.isPending && sorted.length > 0 };
}
