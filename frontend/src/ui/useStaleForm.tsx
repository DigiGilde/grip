/**
 * The save of a form on a record that someone else may have changed.
 *
 * For a form that does not compare field by field: the save goes out on the
 * version the form was opened on; when the server refuses it because the
 * record moved on, the page is refreshed and `panel` shows who changed it and
 * when, with the two ways on (see `@/ui/stale`). A form that can show the
 * other values next to the person's own uses `useStaleRecord` instead.
 */
import { useRef } from 'react';
import { useMutation } from '@tanstack/react-query';
import { errorMessage, type RequestHeaders } from '@/api/client';
import { ConflictPanel } from '@/ui/ConflictPanel';
import { useStaleChoice } from '@/ui/stale';

interface StaleFormOptions<Input, Result> {
  /** The name of the record in a save: its id, or the key the server gives. */
  recordKey: string | null | undefined;
  /** The version of the record as the page holds it now. */
  version: number | null | undefined;
  /** What the form belongs to; when it changes the form starts again. */
  restart?: unknown;
  save: (input: Input, headers?: RequestHeaders) => Promise<Result>;
  /** Refetch what the page shows, so the latest version is known. */
  refresh: () => Promise<unknown>;
  onSaved: (result: Result) => void | Promise<void>;
  onError: (message: string) => void;
  /** Let go of the own input: usually closing the form. */
  onTakeTheirs: () => void;
}

export function useStaleForm<Input, Result>(options: StaleFormOptions<Input, Result>) {
  const stale = useStaleChoice(
    options.recordKey,
    options.version,
    options.refresh,
    options.restart ?? null,
  );
  const last = useRef<Input | null>(null);
  const mutation = useMutation({
    mutationFn: ({ input, onTop }: { input: Input; onTop: boolean }) =>
      options.save(input, onTop ? stale.latestHeaders : stale.headers),
    onSuccess: async (result) => {
      stale.saved();
      await options.onSaved(result);
    },
    onError: async (failure) => {
      if (!(await stale.caught(failure))) options.onError(errorMessage(failure));
    },
  });
  return {
    run: (input: Input) => {
      last.current = input;
      mutation.mutate({ input, onTop: false });
    },
    busy: mutation.isPending,
    panel: stale.conflict ? (
      <ConflictPanel
        conflict={stale.conflict}
        busy={mutation.isPending}
        onKeepMine={() => {
          if (last.current !== null) mutation.mutate({ input: last.current, onTop: true });
        }}
        onTakeTheirs={() => {
          stale.clear();
          options.onTakeTheirs();
        }}
      />
    ) : null,
  };
}
