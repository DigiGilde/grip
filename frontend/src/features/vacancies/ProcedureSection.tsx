import { useState } from 'react';
import { formatDate, formatPeriod } from '@/lib/format';
import {
  publishVacancy,
  setOpeningStep,
  type Channel,
  type OpeningStep,
  type ProcedureStep,
  type Vacancy,
  type VacancyOptions,
} from './api';
import { todayIso, useVacancyChange } from './hooks';
import { CHANNEL_LABELS } from './labels';
import { Button, CheckboxInput, DateInput, TextInput } from './ui';
import { FormSheet, Stack } from '@/ui/layout';
import { useVacancyShell } from './shell';

const OPENING_STEPS: readonly string[] = [
  'internal_opening',
  'priority_candidates',
  'government_wide_opening',
  'external_market',
];
const CHANNELS: Channel[] = ['internal', 'federated', 'recruitment'];

function stepState(step: ProcedureStep): string {
  if (!step.recorded) return 'Nog niet gestart';
  if (step.started_on && step.ended_on && step.started_on === step.ended_on) {
    return formatDate(step.started_on);
  }
  if (step.ended_on) return formatPeriod(step.started_on, step.ended_on);
  return `Loopt sinds ${formatDate(step.started_on)}`;
}

/** The minimum duration of a step, with the first day it may end once it runs. */
function minimumOf(step: ProcedureStep): string | undefined {
  if (!step.minimum_working_days) return undefined;
  const minimum = `Duurt minimaal ${step.minimum_working_days} werkdagen`;
  if (step.recorded && step.earliest_end) {
    return `${minimum}; op zijn vroegst tot en met ${formatDate(step.earliest_end)}`;
  }
  return minimum;
}

function supporting(step: ProcedureStep): string | undefined {
  const parts = [minimumOf(step), step.note].filter(Boolean);
  return parts.length > 0 ? parts.join(' · ') : undefined;
}

function StepSheet({
  vacancy,
  step,
  open,
  onClose,
}: {
  vacancy: Vacancy;
  step: ProcedureStep;
  open: boolean;
  onClose: () => void;
}) {
  const [start, setStart] = useState(step.started_on ?? todayIso());
  const [end, setEnd] = useState(step.ended_on ?? '');
  const [note, setNote] = useState(step.note ?? '');
  const [problem, setProblem] = useState<string | null>(null);
  const change = useVacancyChange(
    vacancy.id,
    (body: { started_on: string; ended_on: string | null; note: string | null }, headers) =>
      setOpeningStep(vacancy.id, step.kind as OpeningStep, body, headers),
    onClose,
    { version: vacancy.version, restart: step.kind },
  );
  const minimum = step.minimum_working_days;

  function submit() {
    setProblem(null);
    if (!start) return setProblem('Vul de begindatum in.');
    change.run({ started_on: start, ended_on: end || null, note: note.trim() || null });
  }

  return (
    <FormSheet
      open={open}
      title={`${step.label} vastleggen`}
      submitText="Leg vast"
      onSubmit={submit}
      onClose={onClose}
      busy={change.busy}
      error={problem ?? change.error}
    >
      {change.panel}
      <DateInput label="Begindatum" value={start} onChange={setStart} required />
      <DateInput
        label="Einddatum"
        hint={
          minimum
            ? `Deze stap duurt minimaal ${minimum} werkdagen. Laat leeg zolang de stap loopt.`
            : 'Laat leeg zolang de stap loopt.'
        }
        value={end}
        onChange={setEnd}
        optional
      />
      <TextInput label="Notitie" value={note} onChange={setNote} multiline optional />
    </FormSheet>
  );
}

export function PublishSheet({
  vacancy,
  options,
  open,
  onClose,
}: {
  vacancy: Vacancy;
  options: VacancyOptions | undefined;
  open: boolean;
  onClose: () => void;
}) {
  const already = vacancy.channels ?? [];
  const [chosen, setChosen] = useState<Channel[]>(already.length > 0 ? already : ['internal']);
  const [day, setDay] = useState(todayIso());
  const [problem, setProblem] = useState<string | null>(null);
  const change = useVacancyChange(
    vacancy.id,
    (input: { channels: Channel[]; day: string }) =>
      publishVacancy(vacancy.id, input.channels, input.day),
    onClose,
  );
  const labels = new Map((options?.channels ?? []).map((option) => [option.value, option.label]));

  function toggle(channel: Channel, on: boolean) {
    setChosen((current) =>
      on ? [...new Set([...current, channel])] : current.filter((entry) => entry !== channel),
    );
  }

  function submit() {
    setProblem(null);
    if (chosen.length === 0) return setProblem('Kies minstens een kanaal.');
    change.run({ channels: chosen, day });
  }

  return (
    <FormSheet
      open={open}
      title={`Vacature ${vacancy.function_title} openstellen`}
      submitText="Stel open"
      onSubmit={submit}
      onClose={onClose}
      busy={change.busy}
      error={problem ?? change.error}
    >
      <nldd-form-section text="Kanalen">
        {CHANNELS.map((channel) => (
          <CheckboxInput
            key={channel}
            label={labels.get(channel) ?? CHANNEL_LABELS[channel]}
            checked={chosen.includes(channel)}
            onChange={(on) => toggle(channel, on)}
          />
        ))}
      </nldd-form-section>
      <DateInput
        label="Start van de interne openstelling"
        hint="De interne openstelling duurt minimaal 5 werkdagen."
        value={day}
        onChange={setDay}
        required
      />
    </FormSheet>
  );
}

/** The steps of the procedure with their dates. Opening itself is the header's action. */
export function ProcedureSection({ vacancy }: { vacancy: Vacancy }) {
  const { openSheet } = useVacancyShell();
  const [stepKind, setStepKind] = useState<string | null>(null);
  const [stepOpen, setStepOpen] = useState(false);

  const canOpen =
    vacancy.permissions.can_edit &&
    vacancy.has_openings === true &&
    (vacancy.status === 'approved' || vacancy.status === 'open');
  const published = vacancy.status === 'open';
  const editableSteps = vacancy.procedure.filter(
    (step) => OPENING_STEPS.includes(step.kind) && (published || step.recorded),
  );
  const selected = vacancy.procedure.find((step) => step.kind === stepKind);

  return (
    <Stack gap="group">
      <nldd-table
        accessible-label="Stappen van de procedure"
        columns="minmax(240px,2fr) minmax(200px,1fr)"
        sm-columns="minmax(0,1.3fr) minmax(0,1fr)"
      >
        <nldd-table-row slot="header">
          <nldd-text-cell text="Stap" />
          <nldd-text-cell text="Wanneer" />
        </nldd-table-row>
        {vacancy.procedure.map((step) => {
          const detail = supporting(step);
          return (
            <nldd-table-row key={step.kind}>
              <nldd-text-cell
                text={`${step.position}. ${step.label}`}
                {...(detail ? { 'supporting-text': detail } : {})}
              />
              <nldd-text-cell
                color={step.recorded ? 'content' : 'secondary'}
                text={stepState(step)}
              />
            </nldd-table-row>
          );
        })}
      </nldd-table>
      {canOpen && published && (
        <nldd-button-group>
          <Button text="Wijzig kanalen" onClick={() => openSheet('publish')} />
          {editableSteps.map((step) => (
            <Button
              key={step.kind}
              text={`${step.recorded ? 'Wijzig' : 'Start'} ${step.label.toLowerCase()}`}
              onClick={() => {
                setStepKind(step.kind);
                setStepOpen(true);
              }}
            />
          ))}
        </nldd-button-group>
      )}
      {canOpen && selected && (
        <StepSheet
          key={`${selected.kind}-${selected.started_on ?? ''}-${selected.ended_on ?? ''}`}
          vacancy={vacancy}
          step={selected}
          open={stepOpen}
          onClose={() => setStepOpen(false)}
        />
      )}
    </Stack>
  );
}
