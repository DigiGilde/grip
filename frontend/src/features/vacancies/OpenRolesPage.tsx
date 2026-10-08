import { useQuery } from '@tanstack/react-query';
import { errorMessage } from '@/api/client';
import { formatPeriod } from '@/lib/format';
import { useInstance } from '@/layout/useInstance';
import { ActionBar } from '@/ui/ActionBar';
import { VACANCY_KEYS, fetchOpenRoles, type OpenRole } from './api';
import { publishedOrigin, scaleAndFte } from './labels';
import { Paragraphs } from './ui';
import { useVacancyViewFilter } from './views';
import { EmptyNotice, ErrorNotice, Loading, Page, Quiet, Section, Stack } from '@/ui/layout';

function roleFacts(role: OpenRole): string {
  return [
    role.fgr_function_name,
    scaleAndFte(role.scale, role.fte),
    formatPeriod(role.start_date, role.end_date),
  ]
    .filter(Boolean)
    .join(' · ');
}

/**
 * The view "Open rollen" of the Vacatures page: published vacancies with
 * their established text, for every person of the instance.
 */
export function OpenRolesPage() {
  const instance = useInstance();
  const roles = useQuery({ queryKey: VACANCY_KEYS.openRoles, queryFn: fetchOpenRoles });
  const viewFilter = useVacancyViewFilter('open');

  return (
    <Page title="Vacatures" instanceName={instance?.name}>
      <ActionBar label="Weergave van de vacatures" filters={[viewFilter]} actions={[]} />
      {roles.isPending && <Loading />}
      {roles.isError && <ErrorNotice message={errorMessage(roles.error)} />}
      {roles.data?.length === 0 && <EmptyNotice text="Er staan nu geen rollen open" />}
      {roles.data && roles.data.length > 0 && (
        <Stack gap="section">
          {roles.data.map((role) => (
            <Section
              key={role.id}
              title={role.function_title}
              {...(roleFacts(role) ? { description: roleFacts(role) } : {})}
            >
              <Paragraphs text={role.text.body} />
              <Quiet>{publishedOrigin(role.text)}</Quiet>
            </Section>
          ))}
        </Stack>
      )}
    </Page>
  );
}
