/**
 * Saving on top of someone else's change.
 *
 * A record people edit in a form carries a `version`. The form sends it back
 * with the save (`ifMatch`); the server refuses the save when the record
 * moved on in between and says who changed it and when. The form then shows
 * what stands there now next to what the person filled in and lets them
 * choose (`ConflictPanel`). Nothing is overwritten unseen and nothing typed
 * is lost: the form keeps its fields until the person has chosen.
 */
import { useCallback, useState } from 'react';
import { ApiError, type RequestHeaders } from '@/api/client';

/** The headers of a save that started from this version of this record. */
export function ifMatch(
  id: string | null | undefined,
  version: number | null | undefined,
): RequestHeaders | undefined {
  if (!id || version === null || version === undefined) return undefined;
  return { 'If-Match': `"${id}:${version}"` };
}

export interface StaleConflict {
  /** The server's sentence: who changed it and when. */
  message: string;
  changedBy: string | null;
  changedAt: string | null;
}

/** The conflict in a failed save, or null when the failure is something else. */
export function staleConflictOf(failure: unknown): StaleConflict | null {
  if (!(failure instanceof ApiError) || failure.status !== 409) return null;
  const problem = failure.problem;
  if (problem?.code !== 'StaleWriteError') return null;
  return {
    message: problem.detail ?? 'Een collega heeft dit intussen gewijzigd.',
    changedBy: typeof problem.changed_by === 'string' ? problem.changed_by : null,
    changedAt: typeof problem.changed_at === 'string' ? problem.changed_at : null,
  };
}

/**
 * The conflict state of one form. `catchStale` takes the failure of a save
 * and says whether it was a conflict; the form then refetches the record and
 * shows the panel.
 */
export function useStaleSave() {
  const [conflict, setConflict] = useState<StaleConflict | null>(null);
  const catchStale = useCallback((failure: unknown): boolean => {
    const found = staleConflictOf(failure);
    setConflict(found);
    return found !== null;
  }, []);
  const clear = useCallback(() => setConflict(null), []);
  return { conflict, catchStale, clear };
}

export interface ConflictValue {
  label: string;
  value: string;
}

/**
 * The conflict of one form together with the record as it stands now.
 *
 * `caught` takes the failure of a save. When it is a conflict it fetches the
 * record again through `refetch` and keeps both, so the form can show the
 * other values next to the person's own; it answers whether it was one.
 */
export function useStaleRecord<R>(refetch: () => Promise<R | null | undefined>) {
  const [theirs, setTheirs] = useState<{ conflict: StaleConflict; record: R } | null>(null);
  const caught = async (failure: unknown): Promise<boolean> => {
    const conflict = staleConflictOf(failure);
    if (conflict === null) return false;
    const record = await refetch().catch(() => null);
    if (record === null || record === undefined) return false;
    setTheirs({ conflict, record });
    return true;
  };
  const clear = useCallback(() => setTheirs(null), []);
  return { theirs, caught, clear };
}
