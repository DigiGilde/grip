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

/**
 * The settings of the instance are saved together and share one version:
 * this is their name in a save.
 */
export const SETTINGS_KEY = 'instance-settings';

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

/**
 * The conflict state of a form that does not compare field by field.
 *
 * `current` is the version of the record as the page holds it now. The form
 * saves on `version`: the one it was opened on. After a refused save the page
 * is refreshed (`refresh`), and the person chooses: save on top of what
 * stands there now (`latestHeaders`), or let go of the own input. `key` is
 * the name of the record in a save: its id, or the key the server gives.
 *
 * `restart` names what the form belongs to (the record, or whether the sheet
 * is open): when it changes, the form starts from the current version again.
 */
export function useStaleChoice(
  key: string | null | undefined,
  current: number | null | undefined,
  refresh: () => Promise<unknown>,
  restart: unknown = null,
) {
  const [opened, setOpened] = useState(current);
  const [conflict, setConflict] = useState<StaleConflict | null>(null);
  const [seen, setSeen] = useState(restart);
  // After a save that went through, the form continues on what it wrote:
  // the version the page holds once it has read the record again.
  const [follow, setFollow] = useState(false);
  if (seen !== restart) {
    setSeen(restart);
    setFollow(false);
    setOpened(current);
    setConflict(null);
  } else if (follow && opened !== current) {
    setFollow(false);
    setOpened(current);
  }
  const caught = async (failure: unknown): Promise<boolean> => {
    const found = staleConflictOf(failure);
    if (found === null) return false;
    await refresh().catch(() => undefined);
    setConflict(found);
    return true;
  };
  /** After a save that went through: the form continues on what it wrote. */
  const saved = useCallback((next?: number | null) => {
    setConflict(null);
    if (next !== null && next !== undefined) setOpened(next);
    else setFollow(true);
  }, []);
  const clear = useCallback(() => setConflict(null), []);
  return {
    /** For the save of the form as it was opened. */
    headers: ifMatch(key, opened),
    /** For a save on top of what stands there now. */
    latestHeaders: ifMatch(key, current),
    conflict,
    caught,
    saved,
    clear,
  };
}
