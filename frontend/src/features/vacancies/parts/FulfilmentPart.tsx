import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { assignmentPartPath } from '@/features/assignments/paths';
import { RouterLinks } from '@/layout/RouterLinks';
import { formatDate, formatFte, formatPercent } from '@/lib/format';
import { ExternalLink } from '@/ui/Icon';
import { type Fact, Facts, LoadError, Loading, Quiet, Section } from '@/ui/layout';
import { DEFAULT_RECRUITMENT_SYSTEM, fetchVacancyHire, hireKey } from '../api';
import {
  RecruitmentRefSheet,
  RemoveRecruitmentRef,
  WithdrawHireSheet,
  WithdrawVacancySheet,
} from '../HireSheets';
import { personPath } from '../paths';
import { useVacancyShell } from '../shell';
import { Button } from '../ui';
import { VacancyPartPage } from '../VacancyPartPage';

function systemName(system: string): string {
  return system.toLowerCase() === DEFAULT_RECRUITMENT_SYSTEM.toLowerCase()
    ? DEFAULT_RECRUITMENT_SYSTEM
    : system;
}

type FulfilmentSheet = 'reference' | 'withdrawHire' | 'withdrawVacancy' | null;

/** The link to the recruitment system, and who was hired. */
function Fulfilment() {
  const { vacancy, parts, openSheet, headerPrimary, nextTask } = useVacancyShell();
  const [sheet, setSheet] = useState<FulfilmentSheet>(null);
  const query = useQuery({
    queryKey: hireKey(vacancy.id),
    queryFn: () => fetchVacancyHire(vacancy.id),
    // The answer to a hire holds the proposed inzet; a refetch would lose it.
    staleTime: Infinity,
  });
  const reference = query.data?.recruitment_ref;
  const hire = query.data?.hire;
  const proposed = hire?.proposed_allocation;
  const staffing = vacancy.assignment_id
    ? assignmentPartPath(vacancy.assignment_id, 'team')
    : null;

  const recruitment: Fact[] = reference
    ? [
        { label: 'Systeem', value: systemName(reference.system) },
        {
          label: 'Kenmerk',
          value: reference.url ? (
            <ExternalLink href={reference.url} text={reference.reference} />
          ) : (
            reference.reference
          ),
        },
      ]
    : [];
  const hired: Fact[] = hire
    ? [
        {
          label: 'Aangenomen',
          value: hire.person_id ? (
            <nldd-link href={personPath(hire.person_id)} text={hire.person_name ?? 'Collega'} />
          ) : (
            (hire.person_name ?? '')
          ),
        },
        { label: 'Start op', value: formatDate(hire.start_date) },
        ...(staffing
          ? [
              {
                label: 'Inzet',
                value: (
                  <nldd-link
                    href={staffing}
                    text={
                      proposed
                        ? `Nog te plannen: ${formatPercent(proposed.fte_pct)} vanaf ${formatDate(proposed.start_date)}`
                        : `Team van ${vacancy.assignment_name ?? 'de opdracht'}`
                    }
                  />
                ),
              },
            ]
          : []),
      ]
    : [];
  // The head carries "Vervul" while that is the reader's next step; then it
  // is not offered a second time here.
  const fillHere =
    vacancy.permissions.can_fill && !hire && !(headerPrimary && nextTask === 'werving.vervullen');
  const atMove = parts.find((part) => part.key === 'fulfilment')?.state === 'current';

  return (
    <>
      {query.isPending && <Loading />}
      {query.isError && <LoadError error={query.error} retry={() => void query.refetch()} />}
      {query.data && (
        <>
          <Section title="Werving">
            {reference && (
              <RouterLinks>
                <Facts label="Verwijzing naar het wervingssysteem" facts={recruitment} />
              </RouterLinks>
            )}
            {!reference && <Quiet>Nog geen verwijzing naar het wervingssysteem</Quiet>}
            <nldd-button-group>
              <Button
                text={reference ? 'Wijzig verwijzing' : 'Leg verwijzing vast'}
                onClick={() => setSheet('reference')}
              />
              {reference && <RemoveRecruitmentRef vacancy={vacancy} />}
            </nldd-button-group>
          </Section>
          <Section title="Vervulling">
            {hire ? (
              <RouterLinks>
                <Facts label="Wie de vacature vervult" facts={hired} />
              </RouterLinks>
            ) : (
              <Quiet>
                {vacancy.status === 'withdrawn'
                  ? 'De vacature is ingetrokken'
                  : `Nog niemand aangenomen voor ${formatFte(vacancy.fte)} fte`}
              </Quiet>
            )}
            {(fillHere || hire || vacancy.permissions.can_withdraw) && (
              <nldd-button-group>
                {fillHere && (
                  <Button
                    text="Vervul"
                    appearance={atMove && !headerPrimary ? 'primary' : 'secondary'}
                    onClick={() => openSheet('hire')}
                  />
                )}
                {hire && (
                  <Button text="Aanname gaat niet door" onClick={() => setSheet('withdrawHire')} />
                )}
                {vacancy.permissions.can_withdraw && (
                  <Button text="Trek vacature in" onClick={() => setSheet('withdrawVacancy')} />
                )}
              </nldd-button-group>
            )}
          </Section>
        </>
      )}
      <RecruitmentRefSheet
        key={`ref-${reference?.system}-${reference?.reference}-${reference?.url}`}
        vacancy={vacancy}
        current={reference}
        open={sheet === 'reference'}
        onClose={() => setSheet(null)}
      />
      <WithdrawHireSheet
        vacancy={vacancy}
        open={sheet === 'withdrawHire'}
        onClose={() => setSheet(null)}
      />
      <WithdrawVacancySheet
        vacancy={vacancy}
        open={sheet === 'withdrawVacancy'}
        onClose={() => setSheet(null)}
      />
    </>
  );
}

export function FulfilmentPart() {
  return (
    <VacancyPartPage part="fulfilment" kind="document" spacing="sections">
      <Fulfilment />
    </VacancyPartPage>
  );
}
