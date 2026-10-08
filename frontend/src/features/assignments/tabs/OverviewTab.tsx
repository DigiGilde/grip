import { ROW_ACTIONS_COLUMN, RowActions } from '@/ui/RowActions';
import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { errorMessage } from '@/api/client';
import { RouterLinks } from '@/layout/RouterLinks';
import { formatDate, formatPeriod } from '@/lib/format';
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
import { assignmentTabPath } from '../paths';
import { useAssignmentShell } from '../shell';
import { useStanding } from '../useStanding';
import {
  Button,
  EmptyNotice,
  ErrorNotice,
  FormSheet,
  SectionHeading,
  SelectInput,
  TextInput,
} from '../ui';

/** Label and value pairs about the assignment; a pair without a value is left out. */
function Facts({ assignment }: { assignment: AssignmentDetail }) {
  const facts: [string, string][] = [
    ['Soort', KIND_LABELS[assignment.kind] ?? assignment.kind],
    ['Opdrachtgever', assignment.client_name ?? ''],
    ['Contactpersoon bij de opdrachtgever', assignment.client_contact ?? ''],
    ['Opdrachtnemer', assignment.contractor_name ?? ''],
    ['Periode', formatPeriod(assignment.start_date, assignment.end_date)],
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
          columns={`minmax(260px,1fr)${canEdit ? ` ${ROW_ACTIONS_COLUMN}` : ''}`}
        >
          <nldd-table-row slot="header">
            <nldd-text-cell text="Node" />
            {canEdit && <nldd-text-cell />}
          </nldd-table-row>
          {refs.map((ref) => (
            <nldd-table-row key={ref}>
              <nldd-cell>
                <nldd-link href={ref} text={ref} target="_blank" rel="noreferrer" />
              </nldd-cell>
              {canEdit && (
                <RowActions
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
 * The way from an idea to an agreed assignment, with the step it is at.
 * Shown while the assignment is still potential.
 */
function NextSteps({ assignment }: { assignment: AssignmentDetail }) {
  const steps = useStanding(assignment);
  const navigate = useNavigate();
  if (!steps) return null;
  const action = steps.action;
  return (
    <nldd-container gap="12">
      <SectionHeading text="Van idee naar opdracht" />
      <RouterLinks>
        <nldd-step-bar accessible-label="Stappen naar een akkoord">
          {steps.steps.map((step) => (
            // Every step says its own state, so the bar never derives one.
            <nldd-step-bar-item
              key={step.key}
              text={step.text}
              status={step.state === 'done' ? 'past' : step.state}
              {...(step.tab && step.state !== 'future'
                ? { href: assignmentTabPath(assignment.id, step.tab) }
                : {})}
            />
          ))}
        </nldd-step-bar>
      </RouterLinks>
      <nldd-text>{steps.advice}</nldd-text>
      {action && (
        <div>
          <Button
            appearance="primary"
            text={action.text}
            onClick={() => navigate(assignmentTabPath(assignment.id, action.tab))}
          />
        </div>
      )}
    </nldd-container>
  );
}

/** The step that needs a word of explanation before it is taken. */
const NEEDS_NOTE = 'verbally_agreed';

function StatusActions({ assignment }: { assignment: AssignmentDetail }) {
  const [problem, setProblem] = useState<string | null>(null);
  const [noting, setNoting] = useState({ open: false, session: 0 });
  const [note, setNote] = useState('');
  const move = useAssignmentMutation(
    ({ target, reason }: { target: string; reason?: string }) =>
      transitionAssignment(assignment.id, target, reason),
    setProblem,
  );
  if (assignment.allowed_transitions.length === 0) return null;
  return (
    <nldd-container gap="12">
      <SectionHeading text="Status wijzigen" />
      {/* What a step still needs (a client, a start date) comes back from
          the server as a sentence; it is shown here as it is. */}
      {problem && !noting.open && <ErrorNotice message={problem} />}
      <nldd-button-group>
        {assignment.allowed_transitions.map((target) => (
          <Button
            key={target}
            text={TRANSITION_LABELS[target] ?? statusLabel(target)}
            appearance={
              target === 'cancelled' || target === 'rejected' ? 'neutral-transparent' : 'secondary'
            }
            loading={move.isPending && move.variables?.target === target}
            onClick={() => {
              if (target === NEEDS_NOTE) {
                setNote('');
                setProblem(null);
                setNoting((current) => ({ open: true, session: current.session + 1 }));
              } else {
                move.mutate({ target });
              }
            }}
          />
        ))}
      </nldd-button-group>
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
    </nldd-container>
  );
}

/** Who and what the assignment is: parties, period, people in charge, context. */
export function OverviewTab() {
  const assignment = useAssignmentShell();
  const [editing, setEditing] = useState({ open: false, session: 0 });
  if (!assignment) return null;
  return (
    <nldd-simple-section>
      <nldd-container gap="24">
        <NextSteps assignment={assignment} />
        <nldd-container gap="12">
          <SectionHeading text="Gegevens" />
          <Facts assignment={assignment} />
          {assignment.permissions.edit_basic && (
            <div>
              <Button
                text="Bewerk gegevens"
                onClick={() =>
                  setEditing((current) => ({ open: true, session: current.session + 1 }))
                }
              />
            </div>
          )}
        </nldd-container>
        <Roles assignment={assignment} />
        <ContextRefs assignment={assignment} />
        <StatusActions assignment={assignment} />
      </nldd-container>
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
