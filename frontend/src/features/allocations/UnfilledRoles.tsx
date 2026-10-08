import { useQuery } from '@tanstack/react-query';
import {
  VACANCY_KEYS,
  fetchUnfilledRoles,
  newVacancyPath,
  type UnfilledRole,
} from '@/features/vacancies/api';
import { RouterLinks } from '@/layout/RouterLinks';
import { formatFte, formatPeriod } from '@/lib/format';
import { SectionHeading } from '@/features/assignments/ui';

function supportingText(role: UnfilledRole): string {
  const period = formatPeriod(role.start_date, role.end_date);
  const open = `${formatFte(role.unfilled_fte)} van ${formatFte(role.fte)} fte niet ingevuld`;
  return period ? `${open}, ${period}` : open;
}

/**
 * Roles on a budget that nobody fills yet, with the way to open a vacancy
 * for each. The list comes from the vacancy module, which returns only the
 * roles the reader may open a vacancy for; for everyone else, and when the
 * list cannot be fetched, the section is simply not there.
 */
export function UnfilledRoles() {
  const roles = useQuery({ queryKey: VACANCY_KEYS.unfilledRoles, queryFn: fetchUnfilledRoles });
  const items = Array.isArray(roles.data) ? roles.data : [];
  if (items.length === 0) return null;
  return (
    <nldd-container gap="8">
      <SectionHeading text="Rollen zonder inzet" />
      <RouterLinks>
        <nldd-list accessible-label="Rollen zonder inzet" appearance="box-base">
          {items.map((role) => (
            <nldd-list-item key={role.budget_line_id} href={newVacancyPath(role.budget_line_id)}>
              <nldd-text-cell
                overline={role.assignment_name}
                text={`${role.role ?? role.description}: maak een vacature`}
                supporting-text={supportingText(role)}
              />
            </nldd-list-item>
          ))}
        </nldd-list>
      </RouterLinks>
    </nldd-container>
  );
}
