import { useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { orUndef, useNlddEvent } from '@/components/nldd/events';
import { assignmentTabPath } from '@/features/assignments/paths';
import { RouterLinks } from '@/layout/RouterLinks';
import { formatDate, formatFte, formatPercent } from '@/lib/format';
import { PATHS } from '@/paths';
import { ErrorNotice, Facts, Loading, Quiet, Section, Stack, type Fact } from '@/ui/layout';
import { errorMessage } from '@/api/client';
import { DEFAULT_RECRUITMENT_SYSTEM, fetchVacancyHire, hireKey } from '../api';
import { DecisionsSection } from '../DecisionsSection';
import {
  RecruitmentRefSheet,
  RemoveRecruitmentRef,
  WithdrawHireSheet,
  WithdrawVacancySheet,
} from '../HireSheets';
import { budgetLineWarning } from '../labels';
import { personPath } from '../paths';
import { ProcedureSection } from '../ProcedureSection';
import { useVacancyShell } from '../shell';
import { requestItems, type RequestItem } from '../steps';
import { RequestFormSection } from '../RequestFormSection';
import { TextWork } from '../TextWork';
import { Button } from '../ui';

const NOT_FILLED = 'Nog niet ingevuld';

/** One thing the request form asks for: ticked when filled, and the way to fill it. */
function RequestRow({ item, onOpen }: { item: RequestItem; onOpen?: () => void }) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'click', onOpen ? () => onOpen() : undefined);
  const done = item.value !== null;
  const state = done ? (item.value ?? '') : NOT_FILLED;
  return (
    <nldd-list-item
      ref={ref}
      size="sm"
      button={orUndef(Boolean(onOpen))}
      {...(onOpen
        ? { 'accessible-label': `${item.label}: ${state}. ${done ? 'Wijzig' : 'Vul in'}` }
        : {})}
    >
      <nldd-icon-cell
        size="20"
        icon={done ? 'check-circle-filled' : 'circle'}
        color={done ? 'success' : 'secondary'}
      />
      <nldd-spacer-cell size="8" />
      <nldd-text-cell width="220px" color="secondary" text={item.label} />
      <nldd-text-cell text={state} color={done ? 'content' : 'secondary'} />
      {onOpen && <nldd-icon-cell size="20" color="secondary" icon="chevron-right" />}
    </nldd-list-item>
  );
}

/** What the request form asks for, filled or visibly not, and the form itself. */
export function RequestTab() {
  const { vacancy, openSheet } = useVacancyShell();
  const editable = vacancy.permissions.can_edit && ['draft', 'requested'].includes(vacancy.status);
  const items = requestItems(vacancy).filter(
    // Who it is addressed to is a name; a reader without names has no such row.
    (item) => item.key !== 'addressee' || 'addressee_name' in vacancy,
  );
  const warning =
    vacancy.scale_fits_budget_line === false
      ? budgetLineWarning(vacancy.scale, vacancy.budget_line_scales)
      : null;
  return (
    <nldd-simple-section>
      <Stack gap="group">
        <RouterLinks>
          <nldd-list accessible-label="Gegevens voor het aanvraagformulier">
            {items.map((item) =>
              item.where === 'texts' ? (
                <nldd-list-item
                  key={item.key}
                  size="sm"
                  href={`${PATHS.vacancies}/${vacancy.id}/tekst`}
                >
                  <nldd-icon-cell
                    size="20"
                    icon={item.value ? 'check-circle-filled' : 'circle'}
                    color={item.value ? 'success' : 'secondary'}
                  />
                  <nldd-spacer-cell size="8" />
                  <nldd-text-cell width="220px" color="secondary" text={item.label} />
                  <nldd-text-cell
                    text={item.value ?? NOT_FILLED}
                    color={item.value ? 'content' : 'secondary'}
                  />
                  <nldd-icon-cell size="20" color="secondary" icon="chevron-right" />
                </nldd-list-item>
              ) : (
                <RequestRow
                  key={item.key}
                  item={item}
                  onOpen={editable ? () => openSheet('prepare') : undefined}
                />
              ),
            )}
          </nldd-list>
        </RouterLinks>
        {warning && <nldd-banner variant="warning" size="sm" text={warning} />}
        {vacancy.permissions.can_download_form && <RequestFormSection vacancyId={vacancy.id} />}
        {editable && (
          <nldd-button-group>
            {editable && (
              <Button
                text="Wijzig functie, fte of periode"
                appearance="neutral-transparent"
                onClick={() => openSheet('edit')}
              />
            )}
          </nldd-button-group>
        )}
      </Stack>
    </nldd-simple-section>
  );
}

export function DecisionsTab() {
  const { vacancy } = useVacancyShell();
  return (
    <nldd-simple-section>
      <DecisionsSection vacancy={vacancy} />
    </nldd-simple-section>
  );
}

export function TextTab() {
  const { vacancy } = useVacancyShell();
  return (
    <nldd-simple-section>
      <TextWork vacancy={vacancy} />
    </nldd-simple-section>
  );
}

export function ProcedureTab() {
  const { vacancy } = useVacancyShell();
  return (
    <nldd-simple-section>
      <ProcedureSection vacancy={vacancy} />
    </nldd-simple-section>
  );
}

function systemName(system: string): string {
  return system.toLowerCase() === DEFAULT_RECRUITMENT_SYSTEM.toLowerCase()
    ? DEFAULT_RECRUITMENT_SYSTEM
    : system;
}

type FulfilmentSheet = 'reference' | 'withdrawHire' | 'withdrawVacancy' | null;

/** The link to the recruitment system, and who was hired. */
export function FulfilmentTab() {
  const { vacancy, openSheet } = useVacancyShell();
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
    ? assignmentTabPath(vacancy.assignment_id, 'staffing')
    : null;

  const recruitment: Fact[] = reference
    ? [
        { label: 'Systeem', value: systemName(reference.system) },
        {
          label: 'Kenmerk',
          value: reference.url ? (
            <nldd-link href={reference.url} text={reference.reference} target="_blank" />
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
                        : `Bemensing van ${vacancy.assignment_name ?? 'de opdracht'}`
                    }
                  />
                ),
              },
            ]
          : []),
      ]
    : [];
  // The step bar carries "Vervul" while that is the current step.
  const fillHere = vacancy.permissions.can_fill && vacancy.status !== 'open' && !hire;

  return (
    <nldd-simple-section>
      {query.isPending && <Loading />}
      {query.isError && <ErrorNotice message={errorMessage(query.error)} />}
      {query.data && (
        <Stack gap="section">
          <Section title="Werving">
            {reference && (
              <RouterLinks>
                <Facts label="Verwijzing naar het wervingssysteem" facts={recruitment} />
              </RouterLinks>
            )}
            <Quiet>Kandidaten staan in het wervingssysteem; grip bewaart ze niet.</Quiet>
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
                {fillHere && <Button text="Vervul" onClick={() => openSheet('hire')} />}
                {hire && (
                  <Button
                    text="Aanname gaat niet door"
                    appearance="neutral-transparent"
                    onClick={() => setSheet('withdrawHire')}
                  />
                )}
                {vacancy.permissions.can_withdraw && (
                  <Button
                    text="Trek vacature in"
                    appearance="neutral-transparent"
                    onClick={() => setSheet('withdrawVacancy')}
                  />
                )}
              </nldd-button-group>
            )}
          </Section>
        </Stack>
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
    </nldd-simple-section>
  );
}
