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
import { Button, CheckboxInput, DateInput, Note, TextInput } from './ui';
import { FormSheet, SectionHeading } from '@/ui/layout';

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
    (body: { started_on: string; ended_on: string | null; note: string | null }) =>
      setOpeningStep(vacancy.id, step.kind as OpeningStep, body),
    onClose,
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

function PublishSheet({
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
      <Note>
        Openstellen kan als het akkoord is gegeven en de vacaturetekst is vastgesteld. Een
        opengestelde vacature is met haar tekst zichtbaar voor iedereen in deze instantie.
      </Note>
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

/** The steps of the procedure with their dates, and opening the vacancy. */
export function ProcedureSection({
  vacancy,
  options,
}: {
  vacancy: Vacancy;
  options: VacancyOptions | undefined;
}) {
  const [stepKind, setStepKind] = useState<string | null>(null);
  const [stepOpen, setStepOpen] = useState(false);
  const [publishing, setPublishing] = useState(false);

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
    <>
      <SectionHeading text="Procedure" />
      {vacancy.has_openings === false && (
        <Note>
          Een vacature voor een beoogde of gerede kandidaat wordt niet opengesteld; daarvoor
          geldt een aparte procedure.
        </Note>
      )}
      <nldd-list appearance="box-base" accessible-label="Stappen van de procedure">
        {vacancy.procedure.map((step) => {
          const detail = supporting(step);
          return (
            <nldd-list-item key={step.kind}>
              <nldd-text-cell
                text={`${step.position}. ${step.label}`}
                {...(detail ? { 'supporting-text': detail } : {})}
              />
              <nldd-spacer-cell size="8" />
              <nldd-text-cell
                width="fit-content"
                color={step.recorded ? 'content' : 'secondary'}
                text={stepState(step)}
              />
            </nldd-list-item>
          );
        })}
      </nldd-list>
      {canOpen && (
        <>
          <nldd-spacer size="8" />
          <nldd-button-group>
            {!published && (
              <Button text="Stel open" appearance="primary" onClick={() => setPublishing(true)} />
            )}
            {published && <Button text="Wijzig kanalen" onClick={() => setPublishing(true)} />}
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
          <PublishSheet
            key={`publish-${vacancy.status}-${(vacancy.channels ?? []).join(',')}`}
            vacancy={vacancy}
            options={options}
            open={publishing}
            onClose={() => setPublishing(false)}
          />
          {selected && (
            <StepSheet
              key={`${selected.kind}-${selected.started_on ?? ''}-${selected.ended_on ?? ''}`}
              vacancy={vacancy}
              step={selected}
              open={stepOpen}
              onClose={() => setStepOpen(false)}
            />
          )}
        </>
      )}
    </>
  );
}
