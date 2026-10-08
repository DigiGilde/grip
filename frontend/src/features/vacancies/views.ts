/**
 * The two views of the Vacatures page: every vacancy the reader may see with
 * where it stands, and the roles that are open now with their text. Each view
 * has its own address; the choice stands first in the bar of the page.
 */
import { useNavigate } from 'react-router-dom';
import { PATHS } from '@/paths';
import type { ActionBarFilter } from '@/ui/ActionBar';

export type VacancyView = 'list' | 'open';

const VIEWS = [
  { value: 'list', label: 'Alle vacatures' },
  { value: 'open', label: 'Open rollen' },
] as const;

export function useVacancyViewFilter(current: VacancyView): ActionBarFilter {
  const navigate = useNavigate();
  return {
    label: 'Weergave',
    value: current,
    onChange: (next) => {
      if (next !== current) navigate(next === 'open' ? PATHS.vacancyOpenRoles : PATHS.vacancies);
    },
    options: VIEWS,
    width: '180px',
  };
}
