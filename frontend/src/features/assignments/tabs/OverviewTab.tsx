import { fetchAssignmentFinance, financeKeys } from '../financeApi';
import { signalText } from '../financeText';
import { ActionBar, type ActionBarAction } from '@/ui/ActionBar';
import { Facts as FactList, Quiet, Section, Stack } from '@/ui/layout';
import { ROW_ACTIONS_COLUMN, RowActions, RowMenu, type RowAction } from '@/ui/RowActions';
import { useState, type ReactNode } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { errorMessage } from '@/api/client';
import { formatDate } from '@/lib/format';
import { AssignmentContextView } from '../../nodes';
import {
  assignmentKeys,
  fetchPersonOptions,
  removeAssignmentRole,
  setAssignmentRole,
  transitionAssignment,
  updateAssignment,
  type AssignmentDetail,
} from '../api';
import { AssignmentFormSheet } from '../AssignmentFormSheet';
import { KIND_LABELS, ROLE_LABELS, TRANSITION_LABELS, statusLabel } from '../labels';
import { useAssignmentShell } from '../shell';
import { ReadOnlyNote } from '../ReadOnlyNote';
import { Button, EmptyNotice, ErrorNotice, FormSheet, SelectInput, TextInput } from '../ui';

/**
 * What the head of the page does not already say: the client and the period
 * stand under the title. A pair without a value is left out.
 */
function Facts({ assignment }: { assignment: AssignmentDetail }) {
  const facts: [string, string][] = [
    ['Soort', KIND_LABELS[assignment.kind] ?? assignment.kind],
    ['Contactpersoon bij de opdrachtgever', assignment.client_contact ?? ''],
    ['Opdrachtnemer', assignment.contractor_name ?? ''],
    [
      'Uitwisseling',
      assignment.shared_with_client_at
        ? `Gedeeld met het grip van de opdrachtgever op ${formatDate(assignment.shared_with_client_at)}`
        : '',
    ],
    [
      'Mondeling akkoord',
      assignment.verbal_agreement_note
        ? [formatDate(assignment.verbal_agreement_at), assignment.verbal_agreement_note]
            .filter(Boolean)
            .join(': ')
        : '',
    ],
    ['Notities', assignment.notes ?? ''],
  ];
  return (
    <FactList
      label="Gegevens van de opdracht"
      labelWidth="320px"
      facts={facts.filter(([, value]) => value !== '').map(([label, value]) => ({ label, value }))}
    />
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

const NO_PERSON = 'Kies een persoon.';

function Roles({ assignment }: { assignment: AssignmentDetail }) {
  // Assigning owner and managers can be a right of its own, without any other edit right.
  // A response from before the right existed falls back on the basic edit right.
  const canEdit = assignment.permissions.manage_roles ?? assignment.permissions.edit_basic;
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
    <Section title="Eigenaar en managers">
      {problem && !adding.open && <ErrorNotice message={problem} />}
      {assignment.roles.length === 0 ? (
        <EmptyNotice text="Deze opdracht heeft nog geen eigenaar" />
      ) : (
        <nldd-table
          accessible-label="Eigenaar en managers"
          columns={`minmax(200px,2fr) 160px${canEdit ? ` ${ROW_ACTIONS_COLUMN}` : ''}`}
        >
          <nldd-table-row slot="header">
            <nldd-text-cell text="Naam" />
            <nldd-text-cell text="Rol" />
            {canEdit && <nldd-text-cell />}
          </nldd-table-row>
          {assignment.roles.map((holder) => (
            <nldd-table-row key={holder.person_id}>
              <nldd-text-cell text={holder.name} />
              <nldd-text-cell text={ROLE_LABELS[holder.role] ?? holder.role} />
              {canEdit && (
                <RowActions
                  name={holder.name}
                  actions={
                    holder.role === 'owner'
                      ? []
                      : [
                          {
                            text: 'Verwijder als manager',
                            destructive: true,
                            confirm: {
                              text: `${holder.name} verwijderen als manager?`,
                              supportingText:
                                'De rechten op deze opdracht die bij de rol horen vervallen.',
                              confirmText: 'Verwijder',
                            },
                            onSelect: () => remove.mutate(holder.person_id),
                          },
                        ]
                  }
                />
              )}
            </nldd-table-row>
          ))}
        </nldd-table>
      )}
      {canEdit && (
        <div>
          <Button
            text="Wijzig eigenaar en managers"
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
        error={adding.open && people.isError ? errorMessage(people.error) : null}
        onClose={() => setAdding((current) => ({ ...current, open: false }))}
        onSubmit={() => {
          if (!personId) {
            setProblem(NO_PERSON);
            return;
          }
          add.mutate(undefined, {
            onSuccess: () => setAdding((current) => ({ ...current, open: false })),
          });
        }}
      >
        <SelectInput
          label="Persoon"
          {...(adding.open && problem === NO_PERSON ? { hint: problem } : {})}
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
          // A refusal is about the role ("Wijs eerst een andere eigenaar aan"): said here.
          hint={
            adding.open && problem && problem !== NO_PERSON
              ? problem
              : 'Een opdracht heeft een eigenaar. De vorige eigenaar wordt manager.'
          }
          value={role}
          onChange={setRole}
          options={Object.entries(ROLE_LABELS).map(([value, label]) => ({
            value,
            label,
          }))}
        />
      </FormSheet>
    </Section>
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
    <Section title="Context">
      {problem && !adding.open && <ErrorNotice message={problem} />}
      {refs.length === 0 ? (
        <EmptyNotice text="Deze opdracht verwijst nog niet naar nodes" />
      ) : (
        // The cards are the references; who may edit removes one from its card.
        <AssignmentContextView
          assignmentId={assignment.id}
          count={refs.length}
          {...(canEdit
            ? {
                actionFor: (ref: string): ReactNode => (
                  <RowMenu
                    name={ref}
                    actions={[
                      {
                        text: 'Verwijder de verwijzing',
                        destructive: true,
                        confirm: {
                          text: 'Deze verwijzing verwijderen?',
                          supportingText: ref,
                          confirmText: 'Verwijder',
                        },
                        onSelect: () => save.mutate(refs.filter((other) => other !== ref)),
                      },
                    ]}
                  />
                ),
              }
            : {})}
        />
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
    </Section>
  );
}

/** The step that needs a word of explanation before it is taken. */
const NEEDS_NOTE = 'verbally_agreed';

/**
 * The status steps the reader may take, as actions for the bar at the top of
 * the tab, with the sheet for the one step that needs a note.
 */
function useStatusActions(assignment: AssignmentDetail): {
  actions: RowAction[];
  problem: string | null;
  sheet: ReactNode;
} {
  const [problem, setProblem] = useState<string | null>(null);
  const [noting, setNoting] = useState({ open: false, session: 0 });
  const [note, setNote] = useState('');
  const move = useAssignmentMutation(
    ({ target, reason }: { target: string; reason?: string }) =>
      transitionAssignment(assignment.id, target, reason),
    setProblem,
  );
  // Leaving the path of an assignment cannot be taken back with a click:
  // it is asked first. The other steps are a choice from the same menu.
  const ENDS: Record<string, string> = {
    cancelled: `${assignment.name} annuleren?`,
    rejected: `${assignment.name} als afgewezen markeren?`,
  };
  const actions: RowAction[] = assignment.allowed_transitions.map((target) => ({
    text: TRANSITION_LABELS[target] ?? statusLabel(target),
    ...(ENDS[target]
      ? {
          destructive: true,
          confirm: {
            text: ENDS[target],
            supportingText: 'De opdracht gaat naar Afgesloten.',
            confirmText: TRANSITION_LABELS[target] ?? 'Bevestig',
          },
        }
      : {}),
    onSelect: () => {
      if (target === NEEDS_NOTE) {
        setNote('');
        setProblem(null);
        setNoting((current) => ({ open: true, session: current.session + 1 }));
      } else {
        move.mutate({ target });
      }
    },
  }));
  const sheet = (
    <FormSheet
      open={noting.open}
      title={`Mondeling akkoord op ${assignment.name}`}
      submitText="Leg vast"
      busy={move.isPending}
      error={noting.open ? problem : null}
      onClose={() => setNoting((current) => ({ ...current, open: false }))}
      onSubmit={() => {
        if (!note.trim()) {
          setProblem('Schrijf op wie akkoord gaf en wat er is afgesproken.');
          return;
        }
        move.mutate(
          { target: NEEDS_NOTE, reason: note.trim() },
          { onSuccess: () => setNoting((current) => ({ ...current, open: false })) },
        );
      }}
    >
      <TextInput
        label="Wat is er afgesproken?"
        hint="Wie gaf akkoord, wanneer, en onder welk voorbehoud. De opdracht blijft potentieel tot het getekende akkoord er is."
        multiline
        value={note}
        onChange={setNote}
        required
      />
    </FormSheet>
  );
  // What a step still needs (a client, a start date) comes back from the
  // server as a sentence; it is shown as it is.
  return { actions, problem: noting.open ? null : problem, sheet };
}

/**
 * The budget differs from the signed quote: said here too, from the same
 * signal as the Financieel tab, so nobody has to find it there.
 */
function AgreedDifference({ assignmentId }: { assignmentId: string }) {
  const query = useQuery({
    queryKey: financeKeys.assignment(assignmentId, 'all'),
    queryFn: () => fetchAssignmentFinance(assignmentId, 'all'),
    retry: false,
  });
  const signal = query.data?.signals.find((item) => item.kind === 'budget_differs_from_agreed');
  if (!signal || !query.data) return null;
  const { variant, text } = signalText(signal, query.data.free_room_threshold_pct);
  return <nldd-banner variant={variant} size="sm" text={text} />;
}

/** Who and what the assignment is: parties, people in charge, context. */
export function OverviewTab() {
  const assignment = useAssignmentShell();
  if (!assignment) return null;
  return <Overview assignment={assignment} />;
}

function Overview({ assignment }: { assignment: AssignmentDetail }) {
  const [editing, setEditing] = useState({ open: false, session: 0 });
  const status = useStatusActions(assignment);
  const actions: ActionBarAction[] = [
    ...(assignment.permissions.edit_basic
      ? [
          {
            text: 'Wijzig gegevens',
            onClick: () => setEditing((current) => ({ open: true, session: current.session + 1 })),
          },
        ]
      : []),
  ];
  return (
    <nldd-simple-section>
      <Stack gap="section">
        <Stack gap="group">
          {assignment.permissions.read_financial && (
            <AgreedDifference assignmentId={assignment.id} />
          )}
          <ActionBar
            label="Acties op de opdracht"
            actions={actions}
            more={{ name: assignment.name, actions: status.actions }}
          />
          {status.problem && <ErrorNotice message={status.problem} />}
          {!assignment.permissions.edit_basic && (
            <ReadOnlyNote assignment={assignment} what="deze gegevens" />
          )}
          {assignment.permissions.edit_basic && !assignment.start_date && (
            <Quiet>
              De opdracht heeft nog geen looptijd. Begrotingsregels en inzet volgen de looptijd: vul
              haar in bij Wijzig gegevens.
            </Quiet>
          )}
          <Facts assignment={assignment} />
        </Stack>
        <Roles assignment={assignment} />
        <ContextRefs assignment={assignment} />
      </Stack>
      {status.sheet}
      <AssignmentFormSheet
        open={editing.open}
        session={editing.session}
        assignment={assignment}
        onClose={() => setEditing((current) => ({ ...current, open: false }))}
        onSaved={() => setEditing((current) => ({ ...current, open: false }))}
      />
    </nldd-simple-section>
  );
}
