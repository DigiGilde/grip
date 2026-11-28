/**
 * "Open this on arrival": an address can ask a page to open one of its
 * panels or sheets, so the button in a head leads to the thing itself and
 * not only to the part it is on. A task leads to the page and asks nothing:
 * its reader takes the step with the page's own button.
 *
 * The page reads the intent, opens what it names and then takes it out of
 * the address, so going back or reloading does not open the panel again.
 */
import { useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';

export function useArrival(param: string): [string | null, () => void] {
  const [searchParams, setSearchParams] = useSearchParams();
  const clear = useCallback(() => {
    setSearchParams(
      (previous) => {
        const next = new URLSearchParams(previous);
        next.delete(param);
        return next;
      },
      { replace: true },
    );
  }, [param, setSearchParams]);
  return [searchParams.get(param), clear];
}
