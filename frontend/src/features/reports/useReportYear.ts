import { useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { currentReportYear, reportYearOptions } from './years';

/** The name of the year in the address, so a view can be linked to with its year. */
export const YEAR_PARAM = 'jaar';

export const pathWithYear = (path: string, year: string) =>
  `${path}?${YEAR_PARAM}=${encodeURIComponent(year)}`;

/**
 * The budget year on screen. It lives in the address (`?jaar=2026`), so a view
 * can be linked to with its year. Anything that is not on offer falls back to
 * the current year.
 */
export function useReportYear(
  options: readonly { value: string }[] = reportYearOptions(),
): [string, (year: string) => void] {
  const [params, setParams] = useSearchParams();
  const asked = params.get(YEAR_PARAM);
  const year =
    asked !== null && options.some((option) => option.value === asked)
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
