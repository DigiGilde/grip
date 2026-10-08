import { useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { YEAR_PARAM } from './topics';
import { currentReportYear, reportYearOptions } from './years';

/**
 * The budget year on screen. It lives in the address (`?jaar=2026`), so it
 * travels from the landing view into a detail view and back, and a view can
 * be linked to with its year. Anything that is not a year on offer falls
 * back to the current year.
 */
export function useReportYear(): [string, (year: string) => void] {
  const [params, setParams] = useSearchParams();
  const asked = params.get(YEAR_PARAM);
  const year =
    asked !== null && reportYearOptions().some((option) => option.value === asked)
      ? asked
      : currentReportYear();
  const setYear = useCallback(
    (next: string) => {
      setParams(
        (current) => {
          const updated = new URLSearchParams(current);
          updated.set(YEAR_PARAM, next);
          return updated;
        },
        { replace: true },
      );
    },
    [setParams],
  );
  return [year, setYear];
}
