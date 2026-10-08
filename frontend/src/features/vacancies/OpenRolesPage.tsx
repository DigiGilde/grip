import { useQuery } from '@tanstack/react-query';
import { errorMessage } from '@/api/client';
import { formatPeriod } from '@/lib/format';
import { useInstance } from '@/layout/useInstance';
import { PageHeading } from '@/pages/PageHeading';
import { VACANCY_KEYS, fetchOpenRoles, type OpenRole } from './api';
import { publishedOrigin, scaleAndFte } from './labels';
import { EmptyNotice, ErrorNotice, Loading, Note, Paragraphs, SectionHeading } from './ui';

function RoleFacts({ role }: { role: OpenRole }) {
  const facts = [
    role.fgr_function_name,
    scaleAndFte(role.scale, role.fte),
    formatPeriod(role.start_date, role.end_date),
  ].filter(Boolean);
  return facts.length > 0 ? <Note>{facts.join(' · ')}</Note> : null;
}

/** Published vacancies with their established text, for every person of the instance. */
export function OpenRolesPage() {
  const instance = useInstance();
  const roles = useQuery({ queryKey: VACANCY_KEYS.openRoles, queryFn: fetchOpenRoles });

  return (
    <nldd-simple-section>
      <PageHeading text="Open rollen" instanceName={instance?.name} />
      {roles.isPending && <Loading />}
      {roles.isError && <ErrorNotice message={errorMessage(roles.error)} />}
      {roles.data?.length === 0 && (
        <EmptyNotice
          text="Er staan nu geen rollen open"
          supportingText="Een vacature verschijnt hier zodra die is opengesteld."
        />
      )}
      {roles.data?.map((role) => (
        <article key={role.id}>
          <nldd-spacer size="24" />
          <SectionHeading text={role.function_title} />
          <RoleFacts role={role} />
          <nldd-spacer size="8" />
          <Paragraphs text={role.text.body} />
          <nldd-spacer size="8" />
          <Note>{publishedOrigin(role.text)}</Note>
        </article>
      ))}
    </nldd-simple-section>
  );
}
