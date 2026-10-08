import { useCallback, useEffect, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, errorMessage } from '@/api/client';
import {
  NOTIFICATIONS_KEY,
  browserState,
  fetchNotifications,
  switchOff,
  switchOn,
  type BrowserState,
} from './api';

/** What the label of a new device is when the person gives none. */
function defaultLabel(): string {
  const agent = navigator.userAgent;
  if (/iPhone|Android.*Mobile/.test(agent)) return 'Telefoon';
  if (/iPad|Android/.test(agent)) return 'Tablet';
  return 'Computer';
}

/**
 * Notifications on this browser: where it stands, and switching on and off.
 * Switching on is what makes the browser ask; nothing here asks on its own.
 */
export function usePush() {
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: NOTIFICATIONS_KEY, queryFn: fetchNotifications });
  const [state, setState] = useState<BrowserState | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    void browserState().then((found) => {
      if (live) setState(found);
    });
    return () => {
      live = false;
    };
  }, []);

  const publicKey = query.data?.public_key ?? null;
  const refresh = useCallback(
    () => queryClient.invalidateQueries({ queryKey: NOTIFICATIONS_KEY }),
    [queryClient],
  );

  const on = useCallback(async () => {
    if (!publicKey) return;
    setBusy(true);
    setError(null);
    try {
      setState(await switchOn(publicKey, defaultLabel()));
      await refresh();
    } catch (failure) {
      // Not grip's answer but the browser's: it could not reach its own
      // push service, or has none.
      setError(
        failure instanceof ApiError
          ? errorMessage(failure)
          : 'Deze browser kon zich niet aanmelden voor meldingen. Probeer het later opnieuw.',
      );
    } finally {
      setBusy(false);
    }
  }, [publicKey, refresh]);

  const off = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      await switchOff();
      setState(await browserState());
      await refresh();
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setBusy(false);
    }
  }, [refresh]);

  return { query, state, busy, error, on, off, refresh };
}
