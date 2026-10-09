import { useRef, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { errorMessage, type RequestHeaders } from '@/api/client';
import { useStaleChoice } from '@/ui/stale';

type Run = (headers?: RequestHeaders) => Promise<unknown>;

/**
 * Runs a change, refreshes everything about the team, and keeps the error of a failed one.
 *
 * With `record` the change is a save of a form on that record: it gets the
 * headers of the version the form was opened on, and a save that is refused
 * because someone changed the record in between ends in `conflict`, which
 * the form shows with the two ways on (see `@/ui/stale`).
 */
export function useSave(
  onDone?: () => void,
  record?: { key: string; version: number | null | undefined },
) {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const stale = useStaleChoice(record?.key, record?.version, () =>
    queryClient.invalidateQueries({ queryKey: ['team'] }),
  );
  const last = useRef<Run | null>(null);
  const mutation = useMutation({
    mutationFn: ({ run, headers }: { run: Run; headers?: RequestHeaders }) => run(headers),
    onSuccess: async () => {
      setError(null);
      stale.saved();
      await queryClient.invalidateQueries({ queryKey: ['team'] });
      onDone?.();
    },
    onError: async (err) => {
      if (await stale.caught(err)) setError(null);
      else setError(errorMessage(err));
    },
  });
  return {
    run: (run: Run) => {
      last.current = run;
      mutation.mutate({ run, headers: stale.headers });
    },
    pending: mutation.isPending,
    error,
    setError,
    /** What `Form` needs to show a refused save and the two ways on. */
    conflict: stale.conflict
      ? {
          conflict: stale.conflict,
          keepMine: () => {
            if (last.current) mutation.mutate({ run: last.current, headers: stale.latestHeaders });
          },
          takeTheirs: () => {
            stale.clear();
            onDone?.();
          },
        }
      : null,
  };
}
