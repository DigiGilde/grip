import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import { ApiError, errorMessage } from '@/api/client';
import { AssignmentOverviewSection } from '@/features/overview/AssignmentOverviewSection';
import { RouterLinks } from '@/layout/RouterLinks';
import { useInstance } from '@/layout/useInstance';
import { formatEuro, formatPeriod } from '@/lib/format';
import { PageHeading } from '@/pages/PageHeading';
import { PATHS } from '@/paths';
import {
  assignmentKeys,
  fetchAssignment,
  fetchPersonOptions,
  removeAssignmentRole,
  setAssignmentRole,
  transitionAssignment,
  updateAssignment,
  type AssignmentDetail,
} from './api';
import { AssignmentContextView } from '../nodes';
import { AssignmentFormSheet } from './AssignmentFormSheet';
import { BudgetEditor } from './BudgetEditor';
import { assignmentMonthClosePath, assignmentQuotePath } from './paths';
import {
  KIND_LABELS,
  ROLE_LABELS,
  STATUS_COLORS,
  TRAFFIC_FORM_LABELS,
  TRANSITION_LABELS,
  statusLabel,
} from './labels';
import {
  Button,
  EmptyNotice,
  ErrorNotice,
  FormSheet,
  Loading,
  SectionHeading,
  SelectInput,
  TextInput,
} from './ui';

/** Label and value pairs about the assignment; a pair without a value is left out. */
function Facts({ assignment }: { assignment: AssignmentDetail }) {
  const facts: [string, string][] = [
    ['Soort', KIND_LABELS[assignment.kind] ?? assignment.kind],
    ['Opdrachtgever', assignment.client_name ?? ''],
    ['Contactpersoon', assignment.client_contact ?? ''],
    ['Periode', formatPeriod(assignment.start_date, assignment.end_date)],
    ['Verkeer', TRAFFIC_FORM_LABELS[assignment.traffic_form] ?? assignment.traffic_form],
    [
      'Offertebedrag',
      'quoted_amount_cents' in assignment ? formatEuro(assignment.quoted_amount_cents) : '',
    ],
    ['Notities', assignment.notes ?? ''],
  ];
  return (
    <nldd-list accessible-label="Gegevens van de opdracht" appearance="box-base">
      {facts
        .filter(([, value]) => value !== '')
        .map(([label, value]) => (
          <nldd-list-item key={label}>
            <nldd-text-cell overline={label} text={value} />
          </nldd-list-item>
        ))}
    </nldd-list>
  );
}

function useAssignmentMutation<T>(
  mutationFn: (variables: T) => Promise<unknown>,
  onProblem: (message: string | null) => void,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    onSuccess: () => {
      onProblem(null);
      void queryClient.invalidateQueries({ queryKey: assignmentKeys.all });
      void queryClient.invalidateQueries({ queryKey: ['overview'] });
    },
    onError: (error) => onProblem(errorMessage(error)),
  });
}

function Roles({ assignment }: { assignment: AssignmentDetail }) {
  const canEdit = assignment.permissions.edit_basic;
  const [problem, setProblem] = useState<string | null>(null);
  const [adding, setAdding] = useState({ open: false, session: 0 });
  const [personId, setPersonId] = useState('');
  const [role, setRole] = useState('manager');
  const people = useQuery({
    queryKey: assignmentKeys.personOptions,
    queryFn: fetchPersonOptions,
    enabled: adding.open,
  });
  const add = useAssignmentMutation(
    () => setAssignmentRole(assignment.id, personId, role),
    setProblem,
  );
  const remove = useAssignmentMutation(
    (id: string) => removeAssignmentRole(assignment.id, id),
    setProblem,
  );

  return (
    <nldd-container gap="12">
      <SectionHeading text="Eigenaar en managers" />
      {problem && !adding.open && <ErrorNotice message={problem} />}
      {assignment.roles.length === 0 ? (
        <EmptyNotice text="Deze opdracht heeft nog geen eigenaar" />
      ) : (
        <nldd-table
          accessible-label="Eigenaar en managers"
          columns={`minmax(200px,2fr) 160px${canEdit ? ' 160px' : ''}`}
        >
          <nldd-table-row slot="header">
            <nldd-text-cell text="Naam" />
            <nldd-text-cell text="Rol" />
            {canEdit && <nldd-text-cell text="Acties" />}
          </nldd-table-row>
          {assignment.roles.map((holder) => (
            <nldd-table-row key={holder.person_id}>
              <nldd-text-cell text={holder.name} />
              <nldd-text-cell text={ROLE_LABELS[holder.role] ?? holder.role} />
              {canEdit && (
                <nldd-cell>
                  {holder.role !== 'owner' && (
                    <Button
                      text="Verwijder"
                      size="sm"
                      appearance="neutral-transparent"
                      accessibleLabel={`Verwijder ${holder.name} als manager`}
                      loading={remove.isPending && remove.variables === holder.person_id}
                      onClick={() => remove.mutate(holder.person_id)}
                    />
                  )}
                </nldd-cell>
              )}
            </nldd-table-row>
          ))}
        </nldd-table>
      )}
      {canEdit && (
        <div>
          <Button
            text="Voeg iemand toe"
            onClick={() => {
              setPersonId('');
              setRole('manager');
              setProblem(null);
              setAdding((current) => ({
                open: true,
                session: current.session + 1,
              }));
            }}
          />
        </div>
      )}
      <FormSheet
        open={adding.open}
        title={`Rol op ${assignment.name}`}
        submitText="Bewaar"
        busy={add.isPending}
        error={
          adding.open ? (problem ?? (people.isError ? errorMessage(people.error) : null)) : null
        }
        onClose={() => setAdding((current) => ({ ...current, open: false }))}
        onSubmit={() => {
          if (!personId) {
            setProblem('Kies een persoon.');
            return;
          }
          add.mutate(undefined, {
            onSuccess: () => setAdding((current) => ({ ...current, open: false })),
          });
        }}
      >
        <SelectInput
          label="Persoon"
          value={personId}
          onChange={setPersonId}
          placeholder="Kies een persoon"
          options={(people.data ?? []).map((p) => ({
            value: p.id,
            label: p.name,
          }))}
          required
        />
        <SelectInput
          label="Rol"
          hint="Een opdracht heeft een eigenaar. De vorige eigenaar wordt manager."
          value={role}
          onChange={setRole}
          options={Object.entries(ROLE_LABELS).map(([value, label]) => ({
            value,
            label,
          }))}
        />
      </FormSheet>
    </nldd-container>
  );
}

function ContextRefs({ assignment }: { assignment: AssignmentDetail }) {
  const canEdit = assignment.permissions.edit_basic;
  const [problem, setProblem] = useState<string | null>(null);
  const [adding, setAdding] = useState({ open: false, session: 0 });
  const [uri, setUri] = useState('');
  const save = useAssignmentMutation(
    (refs: string[]) => updateAssignment(assignment.id, { context_refs: refs }),
    setProblem,
  );
  const refs = assignment.context_refs;

  return (
    <nldd-container gap="12">
      <SectionHeading text="Context" />
      {problem && !adding.open && <ErrorNotice message={problem} />}
      {refs.length > 0 && (
        <AssignmentContextView assignmentId={assignment.id} count={refs.length} />
      )}
      {refs.length === 0 ? (
        <EmptyNotice
          text="Deze opdracht verwijst nog niet naar nodes"
          supportingText="Een verwijzing is de URI van een node in een corpus, bijvoorbeeld een doel of een instrument."
        />
      ) : (
        <nldd-table
          accessible-label="Verwijzingen naar nodes"
          columns={`minmax(260px,1fr)${canEdit ? ' 160px' : ''}`}
        >
          <nldd-table-row slot="header">
            <nldd-text-cell text="Node" />
            {canEdit && <nldd-text-cell text="Acties" />}
          </nldd-table-row>
          {refs.map((ref) => (
            <nldd-table-row key={ref}>
              <nldd-cell>
                <nldd-link href={ref} text={ref} target="_blank" rel="noreferrer" />
              </nldd-cell>
              {canEdit && (
                <nldd-cell>
                  <Button
                    text="Verwijder"
                    size="sm"
                    appearance="neutral-transparent"
                    accessibleLabel={`Verwijder de verwijzing naar ${ref}`}
                    onClick={() => save.mutate(refs.filter((other) => other !== ref))}
                  />
                </nldd-cell>
              )}
            </nldd-table-row>
          ))}
        </nldd-table>
      )}
      {canEdit && (
        <div>
          <Button
            text="Voeg een node toe"
            onClick={() => {
              setUri('');
              setProblem(null);
              setAdding((current) => ({
                open: true,
                session: current.session + 1,
              }));
            }}
          />
        </div>
      )}
      <FormSheet
        open={adding.open}
        title={`Node bij ${assignment.name}`}
        submitText="Bewaar"
        busy={save.isPending}
        error={adding.open ? problem : null}
        onClose={() => setAdding((current) => ({ ...current, open: false }))}
        onSubmit={() => {
          const value = uri.trim();
          if (!/^https?:\/\/\S+$/.test(value)) {
            setProblem('Een verwijzing is een volledige URI die begint met https://.');
            return;
          }
          if (refs.includes(value)) {
            setProblem('Deze node staat al bij de opdracht.');
            return;
          }
          save.mutate([...refs, value], {
            onSuccess: () => setAdding((current) => ({ ...current, open: false })),
          });
        }}
      >
        <TextInput
          label="URI van de node"
          hint="Te vinden op de pagina van de node in het corpus."
          keyboard="url"
          value={uri}
          onChange={setUri}
          required
        />
      </FormSheet>
    </nldd-container>
  );
}

/**
 * The pages that hang under an assignment. A link is shown only to someone
 * the page has something for: the quote is about money, the monthly close
 * about money or about who worked how much.
 */
function RelatedPages({ assignment }: { assignment: AssignmentDetail }) {
  const { read_financial: money, read_staffing: staffing } = assignment.permissions;
  const pages = [
    money && {
      href: assignmentQuotePath(assignment.id),
      text: 'Offerte',
      supporting: 'Een offerte maken uit de begroting, uitgeven en laten tekenen',
    },
    (money || staffing) && {
      href: assignmentMonthClosePath(assignment.id),
      text: 'Maandafsluiting',
      supporting: 'De werkelijke inzet per maand vaststellen en de factuurgegevens',
    },
  ].filter((page) => page !== false);
  if (pages.length === 0) return null;
  return (
    <nldd-container gap="12">
      <SectionHeading text="Offerte en afsluiting" />
      <RouterLinks>
        <nldd-list accessible-label="Offerte en afsluiting van deze opdracht" appearance="box-base">
          {pages.map((page) => (
            <nldd-list-item key={page.href} href={page.href}>
              <nldd-text-cell text={page.text} supporting-text={page.supporting} />
            </nldd-list-item>
          ))}
        </nldd-list>
      </RouterLinks>
    </nldd-container>
  );
}

function StatusActions({ assignment }: { assignment: AssignmentDetail }) {
  const [problem, setProblem] = useState<string | null>(null);
  const move = useAssignmentMutation(
    (target: string) => transitionAssignment(assignment.id, target),
    setProblem,
  );
  return (
    <nldd-container gap="12">
      <div>
        <nldd-badge
          color={STATUS_COLORS[assignment.status] ?? 'neutral'}
          text={statusLabel(assignment.status)}
        />
      </div>
      {problem && <ErrorNotice message={problem} />}
      {assignment.allowed_transitions.length > 0 && (
        <nldd-button-group>
          {assignment.allowed_transitions.map((target) => (
            <Button
              key={target}
              text={TRANSITION_LABELS[target] ?? statusLabel(target)}
              appearance={
                target === 'cancelled' || target === 'rejected'
                  ? 'neutral-transparent'
                  : 'secondary'
              }
              loading={move.isPending && move.variables === target}
              onClick={() => move.mutate(target)}
            />
          ))}
        </nldd-button-group>
      )}
    </nldd-container>
  );
}

export function AssignmentDetailPage() {
  const { assignmentId = '' } = useParams();
  const instance = useInstance();
  const navigate = useNavigate();
  const [editing, setEditing] = useState({ open: false, session: 0 });
  const query = useQuery({
    queryKey: assignmentKeys.detail(assignmentId),
    queryFn: () => fetchAssignment(assignmentId),
    enabled: assignmentId !== '',
    retry: false,
  });
  const assignment = query.data;
  const notFound = query.error instanceof ApiError && query.error.status === 404;

  return (
    <nldd-simple-section>
      <PageHeading text={assignment?.name ?? 'Opdracht'} instanceName={instance?.name} />
      <nldd-container gap="24">
        <div>
          <Button
            text="Terug naar opdrachten"
            appearance="neutral-transparent"
            onClick={() => navigate(PATHS.assignments)}
          />
        </div>
        {query.isPending && <Loading />}
        {query.isError && (
          <ErrorNotice
            message={
              notFound
                ? 'Deze opdracht bestaat niet, of je hebt er geen toegang toe.'
                : errorMessage(query.error)
            }
          />
        )}
        {assignment && (
          <>
            <StatusActions assignment={assignment} />
            <nldd-container gap="12">
              <SectionHeading text="Gegevens" />
              <Facts assignment={assignment} />
              {assignment.permissions.edit_basic && (
                <div>
                  <Button
                    text="Bewerk gegevens"
                    onClick={() =>
                      setEditing((current) => ({
                        open: true,
                        session: current.session + 1,
                      }))
                    }
                  />
                </div>
              )}
            </nldd-container>
            <RelatedPages assignment={assignment} />
            <Roles assignment={assignment} />
            <ContextRefs assignment={assignment} />
            <AssignmentOverviewSection assignmentId={assignment.id} />
            <BudgetEditor assignmentId={assignment.id} />
            <AssignmentFormSheet
              open={editing.open}
              session={editing.session}
              assignment={assignment}
              onClose={() => setEditing((current) => ({ ...current, open: false }))}
              onSaved={() => setEditing((current) => ({ ...current, open: false }))}
            />
          </>
        )}
      </nldd-container>
    </nldd-simple-section>
  );
}
