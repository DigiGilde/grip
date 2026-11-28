import { useQuery } from '@tanstack/react-query';
import { formatPeriod } from '@/lib/format';
import { useInstance } from '@/layout/useInstance';
import { VACANCY_KEYS, fetchOpenRoles, type OpenRole } from './api';
import { publishedOrigin, scaleAndFte } from './labels';
import { Paragraphs } from './ui';
import { vacancyViewTabs } from './views';
import { EmptyNotice, LoadError, Loading, Page, Quiet, Section, Stack } from '@/ui/layout';

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
 * The view "Opengesteld" of the Vacatures page: published vacancies with
 * their established text, for every person of the instance.
 */
export function PublishedPage() {
  const instance = useInstance();
  const roles = useQuery({ queryKey: VACANCY_KEYS.openRoles, queryFn: fetchOpenRoles });

  return (
    <Page
      kind="list"
      title="Vacatures"
      instanceName={instance?.name}
      tabs={vacancyViewTabs('published')}
    >
      {roles.isPending && <Loading />}
      {roles.isError && <LoadError error={roles.error} retry={() => void roles.refetch()} />}
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
