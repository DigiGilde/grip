import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { assignmentKeys, fetchJudgeOptions } from '@/features/assignments/api';
import { formatDate } from '@/lib/format';
import {
  recordDecision,
  type Decision,
  type DecisionInput,
  type DecisionKind,
  type Vacancy,
} from './api';
import { todayIso, useVacancyChange } from './hooks';
import { Button, DateInput, Note, SelectInput, TextInput } from './ui';
import { FormSheet, Stack } from '@/ui/layout';
import { useArrival } from '@/ui/arrival';
import { OpenCell, OpenRow, ROW_ACTIONS_COLUMN, RowActions } from '@/ui/RowActions';

/** What the button says that names who gives an advice or the approval. */
const NAME_TEXT: Record<DecisionKind, string> = {
  hr_advice: 'Noem de HR-adviseur',
  control_advice: 'Noem de controller',
  approval: 'Noem wie akkoord geeft',
};

const KINDS: { kind: DecisionKind; label: string; who: string }[] = [
  { kind: 'hr_advice', label: 'Advies HR', who: 'HR-adviseur' },
  { kind: 'control_advice', label: 'Advies concern control', who: 'Controller' },
  { kind: 'approval', label: 'Akkoord', who: 'Wie akkoord geeft' },
];

/** Choice in the person picker for someone who has no account here. */
const NO_ACCOUNT = 'none';

const VERDICTS = [
  { value: 'yes', label: 'Akkoord' },
  { value: 'no', label: 'Niet akkoord' },
];

function canRecord(vacancy: Vacancy, kind: DecisionKind): boolean {
  const permissions = vacancy.permissions;
  if (kind === 'hr_advice') return permissions.can_record_hr_advice;
  if (kind === 'control_advice') return permissions.can_record_control_advice;
  return permissions.can_record_approval;
}

function outcome(decision: Decision | undefined): string {
  if (!decision) return 'Nog niemand genoemd';
  if (decision.agreed === true) return 'Akkoord';
  if (decision.agreed === false) return 'Niet akkoord';
  return 'Nog geen besluit';
}

function supporting(decision: Decision | undefined): string | undefined {
  if (!decision) return undefined;
  const parts = [
    decision.person_name,
    decision.decided_on ? formatDate(decision.decided_on) : null,
    decision.note,
  ].filter(Boolean);
  return parts.length > 0 ? parts.join(' · ') : undefined;
}

interface SheetState {
  kind: DecisionKind;
  /** Record the decision itself, or only who is named for it. */
  deciding: boolean;
}

function DecisionSheet({
  vacancy,
  state,
  open,
  onClose,
}: {
  vacancy: Vacancy;
  state: SheetState;
  open: boolean;
  onClose: () => void;
}) {
  const meta = KINDS.find((entry) => entry.kind === state.kind) ?? KINDS[0]!;
  const existing = vacancy.decisions.find((decision) => decision.kind === state.kind);
  // The named person records their own decision and cannot rename themselves.
  const namesFixed = state.deciding && !vacancy.permissions.can_edit && existing !== undefined;
  const [name, setName] = useState(existing?.person_name ?? '');
  // Someone already named without an account stays free text; a new name
  // starts at the picker.
  const [personId, setPersonId] = useState(existing && !existing.has_account ? NO_ACCOUNT : '');
  const people = useQuery({
    queryKey: assignmentKeys.judgeOptions,
    queryFn: fetchJudgeOptions,
    enabled: open && !namesFixed,
  });
  const accounts = people.data ?? [];
  // Without the list (it is not for everyone, or it failed) a name can
  // still be typed.
  const freeText = personId === NO_ACCOUNT || (!people.isPending && accounts.length === 0);
  const keepsAccount = personId === '' && existing?.has_account === true;
  const [verdict, setVerdict] = useState(
    existing?.agreed === true ? 'yes' : existing?.agreed === false ? 'no' : '',
  );
  const [note, setNote] = useState(existing?.note ?? '');
  const [day, setDay] = useState(existing?.decided_on ?? todayIso());
  const [problem, setProblem] = useState<string | null>(null);
  const change = useVacancyChange(
    vacancy.id,
    (body: DecisionInput, headers) => recordDecision(vacancy.id, state.kind, body, headers),
    onClose,
    { version: vacancy.version, restart: state.kind },
  );

  function submit() {
    setProblem(null);
    const picked = !namesFixed && !freeText && personId !== '';
    if (!picked && !name.trim()) {
      return setProblem(
        freeText
          ? 'Vul in wie adviseert of akkoord geeft.'
          : 'Kies wie adviseert of akkoord geeft.',
      );
    }
    if (state.deciding && !verdict) return setProblem('Kies akkoord of niet akkoord.');
    change.run({
      ...(picked ? { person_id: personId } : { person_name: name.trim() }),
      ...(state.deciding
        ? { agreed: verdict === 'yes', note: note.trim() || null, decided_on: day || null }
        : {}),
    });
  }

  return (
    <FormSheet
      open={open}
      title={state.deciding ? `${meta.label} vastleggen` : `${meta.who} noemen`}
      submitText={state.deciding ? 'Leg vast' : 'Bewaar'}
      onSubmit={submit}
      onClose={onClose}
      busy={change.busy}
      error={problem ?? change.error}
    >
      {change.panel}
      {namesFixed ? (
        <Note>Je legt dit vast als {existing?.person_name}.</Note>
      ) : (
        <>
          {accounts.length > 0 && (
            <SelectInput
              label={meta.who}
              hint="Iemand met een account legt het besluit zelf vast."
              value={personId}
              onChange={setPersonId}
              options={[
                ...accounts.map((person) => ({ value: person.id, label: person.name })),
                { value: NO_ACCOUNT, label: 'Iemand zonder account' },
              ]}
              placeholder={keepsAccount ? (existing?.person_name ?? 'Kies') : 'Kies'}
              required={!keepsAccount}
            />
          )}
          {freeText && (
            <TextInput
              label={accounts.length > 0 ? 'Naam' : meta.who}
              hint="Deze persoon gebruikt grip niet; iemand anders legt het besluit vast."
              value={name}
              onChange={setName}
              required
            />
          )}
        </>
      )}
      {state.deciding && (
        <>
          <SelectInput
            label="Besluit"
            value={verdict}
            onChange={setVerdict}
            options={VERDICTS}
            placeholder="Kies"
            required
          />
          <DateInput label="Datum" value={day} onChange={setDay} required />
          <TextInput label="Toelichting" value={note} onChange={setNote} multiline optional />
        </>
      )}
    </FormSheet>
  );
}

/** Advice from HR and concern control, and the approval. */
export function DecisionsSection({ vacancy }: { vacancy: Vacancy }) {
  const [state, setState] = useState<SheetState>({ kind: 'hr_advice', deciding: false });
  const [open, setOpen] = useState(false);
  const requested = vacancy.status !== 'draft';

  function show(kind: DecisionKind, deciding: boolean) {
    setState({ kind, deciding });
    setOpen(true);
  }

  // While the vacancy waits for advice and approval, the first decision the
  // reader can record is the one primary action of this view.
  const waiting = vacancy.status === 'requested';
  const firstToRecord = KINDS.find(({ kind }) => {
    const decision = vacancy.decisions.find((entry) => entry.kind === kind);
    return canRecord(vacancy, kind) && decision?.agreed !== true && decision?.agreed !== false;
  })?.kind;

  const first = KINDS.find((entry) => entry.kind === firstToRecord);
  // Nothing to record yet, but someone must be named: the first advice or
  // approval without a name, for who may name.
  const toName =
    waiting && !first && vacancy.permissions.can_edit
      ? KINDS.find(({ kind }) => !vacancy.decisions.some((entry) => entry.kind === kind))
      : undefined;
  // The head of the vacancy, a task or a link can ask for one of the three:
  // its panel opens on arrival, to record when the reader may, else to name.
  const [wanted, arrived] = useArrival('besluit');
  const [handled, setHandled] = useState<string | null>(null);
  if (wanted !== null && handled !== wanted) {
    setHandled(wanted);
    const found = KINDS.find((entry) => entry.kind === wanted);
    if (found && requested) {
      if (canRecord(vacancy, found.kind)) show(found.kind, true);
      else if (vacancy.permissions.can_edit) show(found.kind, false);
    }
  }
  useEffect(() => {
    if (wanted !== null) arrived();
  }, [wanted, arrived]);

  return (
    <Stack gap="group">
      {waiting && first && (
        <nldd-button-group>
          <Button
            text={`Leg ${first.label.charAt(0).toLowerCase()}${first.label.slice(1)} vast`}
            appearance="primary"
            onClick={() => show(first.kind, true)}
          />
        </nldd-button-group>
      )}
      {toName && (
        <nldd-button-group>
          <Button
            text={NAME_TEXT[toName.kind]}
            appearance="primary"
            onClick={() => show(toName.kind, false)}
          />
        </nldd-button-group>
      )}
      <nldd-table
        accessible-label="Advies en akkoord"
        columns={`minmax(180px,1fr) 200px minmax(200px,1.5fr) ${ROW_ACTIONS_COLUMN}`}
        sm-columns={`minmax(140px,1fr) minmax(120px,1fr) ${ROW_ACTIONS_COLUMN}`}
      >
        <nldd-table-row slot="header">
          <nldd-text-cell text="Onderdeel" />
          <nldd-text-cell text="Besluit" />
          <nldd-text-cell text="Door" hide-below="md" />
          <nldd-cell />
        </nldd-table-row>
        {KINDS.map(({ kind, label, who }) => {
          const decision = vacancy.decisions.find((entry) => entry.kind === kind);
          const decided = decision?.agreed === true || decision?.agreed === false;
          const records = requested && canRecord(vacancy, kind);
          const names = requested && vacancy.permissions.can_edit && !decided;
          const onOpen = records
            ? () => show(kind, true)
            : names
              ? () => show(kind, false)
              : undefined;
          const verb = records ? (decided ? 'Wijzig' : 'Leg vast') : decision ? 'Wijzig' : 'Noem';
          return (
            <OpenRow key={kind} onOpen={onOpen}>
              <OpenCell
                text={label}
                onOpen={onOpen}
                accessibleLabel={
                  records ? `${verb}: ${label.toLowerCase()}` : `${verb} ${who.toLowerCase()}`
                }
              />
              <nldd-text-cell text={outcome(decision)} color={decided ? 'content' : 'secondary'} />
              <nldd-text-cell hide-below="md" text={supporting(decision) ?? ''} />
              <RowActions
                name={label}
                actions={
                  records && names
                    ? [
                        {
                          text: decision ? `Wijzig wie het geeft` : `Noem wie het geeft`,
                          onSelect: () => show(kind, false),
                        },
                      ]
                    : []
                }
              />
            </OpenRow>
          );
        })}
      </nldd-table>
      <DecisionSheet
        // A fresh form for each decision and each saved state of it.
        key={`${state.kind}-${state.deciding}-${JSON.stringify(vacancy.decisions.find((d) => d.kind === state.kind) ?? null)}`}
        vacancy={vacancy}
        state={state}
        open={open}
        onClose={() => setOpen(false)}
      />
    </Stack>
  );
}
