import { useEffect, useState, type ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, errorMessage } from '@/api/client';
import { RouterLinks } from '@/layout/RouterLinks';
import { formatDate } from '@/lib/format';
import { ExternalLink } from '@/ui/Icon';
import { ErrorNotice, FormSheet, LoadError, Loading, Quiet, Section, Stack } from '@/ui/layout';
import { VACANCY_KEYS, type TextKind, type Vacancy } from './api';
import { todayIso } from './hooks';
import { TEXT_KIND_LABELS } from './labels';
import { useCaseCourse } from '@/features/tasks/course';
import { useArrival } from '@/ui/arrival';
import { unknownFacts } from '@/ui/text/facts';
import { useStaleForm } from '@/ui/useStaleForm';
import { courseLine } from '@/ui/course';
import { TailoredSheet } from './TailoredSheet';
import { factHref } from './factHref';
import { vacancyTextWritePath } from './paths';
import { useVacancyShell } from './shell';
import { StructuredText } from './StructuredText';
import {
  TEXT_WORK_KEY,
  addRemark,
  fetchTextWork,
  giveVerdict,
  offerForReview,
  removePublication,
  resolveRemark,
  saveVersion,
  setPublication,
  settleVersion,
  splitSections,
  useStandardText as startFromStandardText,
  wantVacancyText,
  withdrawReview,
  type Publication,
  type Remark,
  type Round,
  type TextWork as Work,
  type ActionKey,
  type VacancyTextWork,
} from './textWorkApi';
import { Button, CheckboxInput, DateInput, QuietButton, SelectInput, TextInput } from './ui';

const STATE_COLORS: Record<Work['state'], 'neutral' | 'warning' | 'success' | 'accent'> = {
  none: 'neutral',
  draft: 'neutral',
  in_review: 'accent',
  returned: 'warning',
  agreed: 'success',
  settled: 'success',
};

const ROUND_WORDS: Record<Round['outcome'], string> = {
  open: 'wacht op een oordeel',
  agreed: 'akkoord',
  returned: 'terug met opmerkingen',
  withdrawn: 'teruggenomen door de schrijver',
};

const PLACES: { value: Publication['place']; label: string }[] = [
  { value: 'government_wide', label: 'Werken voor Nederland' },
  { value: 'internal', label: 'Intern' },
  { value: 'external', label: 'Een externe vacaturesite' },
];

/** A change to the text work; the answer is the work as the viewer now sees it. */
function useWorkChange<Input>(
  vacancyId: string,
  change: (input: Input) => Promise<VacancyTextWork>,
  onDone?: () => void,
) {
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: change,
    onSuccess: (work) => {
      queryClient.setQueryData(TEXT_WORK_KEY(vacancyId), work);
      // The vacancy shows the settled text and the tasks follow the facts.
      void queryClient.invalidateQueries({ queryKey: VACANCY_KEYS.detail(vacancyId) });
      void queryClient.invalidateQueries({ queryKey: ['tasks'] });
      onDone?.();
    },
    onError: (error) => {
      // Someone else saved in between: show their version behind the form.
      if (error instanceof ApiError && error.status === 409) {
        void queryClient.invalidateQueries({ queryKey: TEXT_WORK_KEY(vacancyId) });
      }
    },
  });
  return {
    run: mutation.mutate,
    busy: mutation.isPending,
    error: mutation.isError ? errorMessage(mutation.error) : null,
    conflict: mutation.error instanceof ApiError && mutation.error.status === 409,
    reset: mutation.reset,
  };
}

type Sheet =
  | { kind: 'write'; text: TextKind; start: string; basedOn: string | null }
  | { kind: 'offer'; text: TextKind }
  | { kind: 'judge'; text: TextKind; reviewId: string }
  | { kind: 'tailored' }
  | { kind: 'remark'; text: TextKind; parent?: Remark }
  | { kind: 'publication' };

/** Why a vacancy for a known candidate has no vacancy text. */
const NOT_OPENED =
  'Deze vacature wordt niet opengesteld: de kandidaat is bekend. Een vacaturetekst is daarom niet nodig.';

function who(name: string | null | undefined, fallback = 'een collega'): string {
  return name ?? fallback;
}

function WriteSheet({
  vacancyId,
  sheet,
  work,
  onClose,
}: {
  vacancyId: string;
  sheet: Extract<Sheet, { kind: 'write' }>;
  work: Work;
  onClose: () => void;
}) {
  const [body, setBody] = useState(sheet.start);
  const [problem, setProblem] = useState<string | null>(null);
  const latest = work.versions[work.versions.length - 1];
  // After a conflict the save starts from the version that came in between.
  const [basedOn, setBasedOn] = useState(sheet.basedOn);
  const change = useWorkChange(
    vacancyId,
    (text: string) => saveVersion(vacancyId, sheet.text, text, basedOn),
    onClose,
  );
  const label = TEXT_KIND_LABELS[sheet.text];
  const moved = change.conflict && latest && latest.id !== sheet.basedOn;
  if (moved && basedOn !== latest.id) setBasedOn(latest.id);

  return (
    <FormSheet
      open
      title={sheet.basedOn ? `${label} aanpassen` : `${label} schrijven`}
      submitText="Bewaar"
      onSubmit={() => {
        setProblem(null);
        if (!body.trim()) return setProblem('De tekst is leeg.');
        change.run(body.trim());
      }}
      onClose={onClose}
      busy={change.busy}
      error={problem ?? change.error}
    >
      {/* The motivation goes into a field of the request form that holds
          plain text only, so it is written as plain text. */}
      <TextInput label={label} value={body} onChange={setBody} multiline required />
      {moved && (
        <Stack gap="close">
          <Quiet>
            Versie {latest.number} van {who(latest.created_by_name)}:
          </Quiet>
          <StructuredText text={latest.body} headingLevel={4} />
        </Stack>
      )}
    </FormSheet>
  );
}

function OfferSheet({
  vacancyId,
  kind,
  work,
  options,
  onClose,
}: {
  vacancyId: string;
  kind: TextKind;
  work: Work;
  options: { id: string; name: string }[];
  onClose: () => void;
}) {
  const [chosen, setChosen] = useState<string[]>(work.default_reviewer_ids ?? []);
  const [note, setNote] = useState('');
  const [problem, setProblem] = useState<string | null>(null);
  const change = useWorkChange(
    vacancyId,
    () => offerForReview(vacancyId, kind, chosen, note),
    onClose,
  );
  return (
    <FormSheet
      open
      title={`Vraag om een oordeel over de ${TEXT_KIND_LABELS[kind].toLowerCase()}`}
      submitText="Vraag om een oordeel"
      onSubmit={() => {
        setProblem(null);
        if (chosen.length === 0) return setProblem('Kies wie de tekst beoordeelt.');
        change.run(undefined);
      }}
      onClose={onClose}
      busy={change.busy}
      error={problem ?? change.error}
    >
      <nldd-form-field label="Wie beoordeelt de tekst">
        <Stack gap="close">
          {options.map((person) => (
            <CheckboxInput
              key={person.id}
              label={person.name}
              checked={chosen.includes(person.id)}
              onChange={(checked) =>
                setChosen((current) =>
                  checked ? [...current, person.id] : current.filter((id) => id !== person.id),
                )
              }
            />
          ))}
        </Stack>
      </nldd-form-field>
      <TextInput
        label="Waar wil je een oordeel over"
        value={note}
        onChange={setNote}
        multiline
        optional
      />
    </FormSheet>
  );
}

function JudgeSheet({
  vacancyId,
  sheet,
  onClose,
}: {
  vacancyId: string;
  sheet: Extract<Sheet, { kind: 'judge' }>;
  onClose: () => void;
}) {
  const [verdict, setVerdict] = useState<'agreed' | 'remarks'>('agreed');
  const [note, setNote] = useState('');
  const change = useWorkChange(
    vacancyId,
    () => giveVerdict(vacancyId, sheet.reviewId, verdict, note),
    onClose,
  );
  return (
    <FormSheet
      open
      title={`Je oordeel over de ${TEXT_KIND_LABELS[sheet.text].toLowerCase()}`}
      submitText="Geef je oordeel"
      onSubmit={() => change.run(undefined)}
      onClose={onClose}
      busy={change.busy}
      error={change.error}
    >
      <SelectInput
        label="Oordeel"
        value={verdict}
        onChange={(value) => setVerdict(value as 'agreed' | 'remarks')}
        options={[
          { value: 'agreed', label: 'Akkoord' },
          { value: 'remarks', label: 'Terug met opmerkingen' },
        ]}
      />
      <TextInput
        label="Toelichting"
        value={note}
        onChange={setNote}
        multiline
        optional={verdict === 'agreed'}
      />
    </FormSheet>
  );
}

function RemarkSheet({
  vacancyId,
  sheet,
  work,
  onClose,
}: {
  vacancyId: string;
  sheet: Extract<Sheet, { kind: 'remark' }>;
  work: Work;
  onClose: () => void;
}) {
  const latest = work.versions[work.versions.length - 1];
  const sections = latest ? splitSections(latest.text).filter((section) => section.heading) : [];
  const [section, setSection] = useState(sheet.parent?.section ?? '');
  const [body, setBody] = useState('');
  const [problem, setProblem] = useState<string | null>(null);
  const change = useWorkChange(
    vacancyId,
    () => addRemark(vacancyId, sheet.text, body.trim(), section, sheet.parent?.id),
    onClose,
  );
  return (
    <FormSheet
      open
      title={sheet.parent ? 'Antwoord op de opmerking' : 'Plaats een opmerking'}
      submitText={sheet.parent ? 'Antwoord' : 'Plaats de opmerking'}
      onSubmit={() => {
        setProblem(null);
        if (!body.trim()) return setProblem('De opmerking is leeg.');
        change.run(undefined);
      }}
      onClose={onClose}
      busy={change.busy}
      error={problem ?? change.error}
    >
      {!sheet.parent && sections.length > 0 && (
        <SelectInput
          label="Bij welk onderdeel"
          value={section}
          onChange={setSection}
          options={[
            { value: '', label: 'De hele tekst' },
            ...sections.map((item) => ({ value: item.heading, label: item.heading })),
          ]}
        />
      )}
      <TextInput
        label={sheet.parent ? 'Antwoord' : 'Opmerking'}
        value={body}
        onChange={setBody}
        multiline
        required
      />
    </FormSheet>
  );
}

function PublicationSheet({ vacancy, onClose }: { vacancy: Vacancy; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [place, setPlace] = useState<Publication['place']>('government_wide');
  const [url, setUrl] = useState('');
  const [day, setDay] = useState(todayIso());
  const [problem, setProblem] = useState<string | null>(null);
  const change = useStaleForm({
    recordKey: vacancy.id,
    version: vacancy.version,
    save: (_input: undefined, headers) =>
      setPublication(vacancy.id, place, url.trim(), day, headers),
    refresh: () => queryClient.invalidateQueries({ queryKey: VACANCY_KEYS.detail(vacancy.id) }),
    onSaved: (work) => {
      queryClient.setQueryData(TEXT_WORK_KEY(vacancy.id), work);
      void queryClient.invalidateQueries({ queryKey: VACANCY_KEYS.detail(vacancy.id) });
      void queryClient.invalidateQueries({ queryKey: ['tasks'] });
      onClose();
    },
    onError: setProblem,
    onTakeTheirs: onClose,
  });
  return (
    <FormSheet
      open
      title="Link naar de gepubliceerde vacature"
      submitText="Leg vast"
      onSubmit={() => {
        setProblem(null);
        if (!url.trim().startsWith('https://')) {
          return setProblem('Geef het adres van de vacature, beginnend met https://.');
        }
        change.run(undefined);
      }}
      onClose={onClose}
      busy={change.busy}
      error={problem}
    >
      {change.panel}
      <SelectInput
        label="Waar staat de vacature"
        value={place}
        onChange={(value) => setPlace(value as Publication['place'])}
        options={PLACES}
      />
      <TextInput
        label="Adres van de vacature"
        hint="Het adres dat iedereen kan openen, niet de link in het wervingssysteem."
        value={url}
        onChange={setUrl}
        keyboard="url"
        required
      />
      <DateInput label="Gepubliceerd op" value={day} onChange={setDay} />
    </FormSheet>
  );
}

function RemarkItem({
  vacancyId,
  remark,
  mayAct,
  onAnswer,
}: {
  vacancyId: string;
  remark: Remark;
  mayAct: boolean;
  onAnswer: () => void;
}) {
  const resolve = useWorkChange(vacancyId, () =>
    resolveRemark(vacancyId, remark.id, !remark.resolved_at),
  );
  return (
    <Stack gap="close">
      <nldd-text>
        {remark.section ? `${remark.section}: ` : ''}
        {remark.body}
      </nldd-text>
      <Quiet>
        {remark.by_viewer ? 'Jij' : who(remark.author_name)} op {formatDate(remark.created_at)}
        {remark.version_number ? `, bij versie ${remark.version_number}` : ''}
        {remark.resolved_at ? '. Afgehandeld.' : ''}
      </Quiet>
      {remark.answers.map((answer) => (
        <Quiet key={answer.id}>
          {answer.by_viewer ? 'Jij' : who(answer.author_name)}: {answer.body}
        </Quiet>
      ))}
      {resolve.error && <ErrorNotice message={resolve.error} />}
      {mayAct && (
        <nldd-button-group>
          <QuietButton text="Antwoord" size="sm" onClick={onAnswer} />
          <QuietButton
            text={remark.resolved_at ? 'Zet weer open' : 'Markeer als afgehandeld'}
            size="sm"
            loading={resolve.busy}
            onClick={() => resolve.run(undefined)}
          />
        </nldd-button-group>
      )}
    </Stack>
  );
}

function roundLine(round: Round): string {
  const names = round.verdicts
    .map((verdict) => (verdict.is_viewer ? 'jij' : verdict.reviewer_name))
    .filter(Boolean)
    .join(', ');
  const by = names ? ` (${names})` : '';
  return `Ronde ${round.round}, versie ${round.version_number}, ${formatDate(round.offered_at)}: ${ROUND_WORDS[round.outcome]}${by}`;
}

function TextBlock({
  vacancy,
  work,
  data,
  open,
  leading,
  whose,
}: {
  vacancy: Vacancy;
  work: Work;
  data: VacancyTextWork;
  /** Whose move it is, from the course of this text; said when the text itself does not. */
  whose?: string | undefined;
  open: (sheet: Sheet) => void;
  /**
   * The one text on the screen whose next step leads. The page header holds
   * the primary action of the vacancy, so the step leads as a secondary
   * button; only a reviewer, who has no action in the header, gets a primary.
   */
  leading: boolean;
}) {
  const [showAll, setShowAll] = useState(false);
  const { headerPrimary } = useVacancyShell();
  const latest = work.versions[work.versions.length - 1];
  const settled = [...work.versions].reverse().find((version) => version.settled_at);
  const start = useWorkChange(vacancy.id, () => startFromStandardText(vacancy.id));
  const settle = useWorkChange(vacancy.id, (id: string) => settleVersion(vacancy.id, id));
  const withdraw = useWorkChange(vacancy.id, (id: string) => withdrawReview(vacancy.id, id));
  const round = work.rounds[work.rounds.length - 1];
  const label = TEXT_KIND_LABELS[work.kind];
  const isVacancyText = work.kind === 'vacancy_text';
  const standard = work.standard_text;

  const navigate = useNavigate();
  // The vacancy text is written on a page of its own; the motivation, a few
  // plain sentences for the request form, in a sheet.
  function write(startText: string, basedOn: string | null) {
    if (isVacancyText) navigate(vacancyTextWritePath(vacancy.id));
    else open({ kind: 'write', text: work.kind, start: startText, basedOn });
  }

  // A text with passages still to fill is not ready for anyone else: the
  // next step is to write on, whatever the workflow would offer otherwise.
  const unfinished = work.may_write && latest !== undefined && work.open_passages.length > 0;
  const step: ActionKey =
    unfinished && ['offer', 'settle'].includes(work.action.key) ? 'write' : work.action.key;
  const stepText = step === work.action.key ? work.action.text : 'Schrijf verder';

  function act() {
    if (step === 'start') start.run(undefined);
    else if (step === 'write') write(latest?.body ?? '', latest?.id ?? null);
    else if (step === 'process' || step === 'revise') write(latest?.body ?? '', latest?.id ?? null);
    else if (step === 'offer') open({ kind: 'offer', text: work.kind });
    else if (step === 'withdraw' && round) withdraw.run(round.id);
    else if (step === 'judge' && work.viewer_review_id) {
      open({ kind: 'judge', text: work.kind, reviewId: work.viewer_review_id });
    } else if (step === 'settle' && latest) settle.run(latest.id);
  }

  // Everything else this reader can do with the text: real buttons beside
  // the next step, never bare text.
  const others: ReactNode[] = [];
  if (work.may_write && latest && !['write', 'process', 'revise'].includes(step)) {
    others.push(
      <Button key="write" text="Schrijf verder" onClick={() => write(latest.body, latest.id)} />,
    );
  }
  if (work.may_write && !latest && step !== 'write') {
    others.push(<Button key="own" text="Schrijf zelf" onClick={() => write('', null)} />);
  }
  if (isVacancyText && work.may_write && standard && data.drafting_available) {
    others.push(
      <Button
        key="tailored"
        text="Stel een tekst op maat op"
        onClick={() => open({ kind: 'tailored' })}
      />,
    );
  }
  if (work.may_settle && latest && step !== 'settle' && !unfinished) {
    others.push(
      <Button
        key="settle"
        text="Stel vast"
        loading={settle.busy}
        onClick={() => settle.run(latest.id)}
      />,
    );
  }
  if (work.may_remark && latest) {
    others.push(
      <Button
        key="remark"
        text="Plaats een opmerking"
        onClick={() => open({ kind: 'remark', text: work.kind })}
      />,
    );
  }

  // Facts the draft names that are filled in somewhere else.
  const elsewhere = latest && work.may_write ? unknownFacts(latest.body, work.facts) : [];
  const error = start.error ?? settle.error ?? withdraw.error;
  const earlier = work.versions.slice(0, -1).reverse();
  return (
    <Section title={label}>
      <nldd-container layout="row" gap="8" vertical-alignment="center">
        <nldd-tag color={STATE_COLORS[work.state]} text={work.state_text} />
        {(work.with_whom ?? whose) && <Quiet>{work.with_whom ?? whose}</Quiet>}
      </nldd-container>
      {work.revising && settled && (
        <Quiet>
          De tekst die op {formatDate(settled.settled_at)} is vastgesteld, wordt aangepast. Tot de
          nieuwe versie is vastgesteld geldt de oude.
        </Quiet>
      )}
      {work.kind === 'motivation' && work.state !== 'settled' && vacancy.status !== 'draft' && (
        <Quiet>
          De aanvraag is ingediend zonder vastgestelde motivatie. Op het aanvraagformulier staat er
          geen.
        </Quiet>
      )}
      {!work.needed && <Quiet>{NOT_OPENED}</Quiet>}
      {work.state === 'none' && isVacancyText && standard && (
        <Quiet>
          {standard.match === 'function_group'
            ? `Voor deze rol is geen standaardtekst. De tekst van ${standard.role} lijkt er het meest op.`
            : `Er is een standaardtekst voor ${standard.role}.`}
          {standard.unread ? ' Die tekst is afgeleid en nog niet nagelezen.' : ''}
        </Quiet>
      )}
      {isVacancyText && data.context === 'unreachable' && (
        <Quiet>Opgesteld zonder de context uit het corpus: dat was niet bereikbaar.</Quiet>
      )}
      {latest && <StructuredText text={latest.text} />}
      {latest && (
        <Quiet>
          Versie {latest.number} van {formatDate(latest.created_at)}
          {latest.created_by_name ? `, ${latest.created_by_name}` : ''}
          {latest.origin ? `. ${latest.origin}` : ''}
          {latest.settled_at
            ? `. Vastgesteld op ${formatDate(latest.settled_at)}${latest.settled_by_name ? ` door ${latest.settled_by_name}` : ''}`
            : ''}
          .
        </Quiet>
      )}
      {work.open_passages.length > 0 && work.state !== 'settled' && (
        <Quiet>
          {work.open_passages.length === 1
            ? 'Nog 1 plek in te vullen voor je de tekst kunt voorleggen of vaststellen'
            : `Nog ${work.open_passages.length} plekken in te vullen voor je de tekst kunt voorleggen of vaststellen`}
        </Quiet>
      )}
      {elsewhere.length > 0 && work.state !== 'settled' && (
        <RouterLinks>
          <Stack gap="close">
            {elsewhere.map((fact) => (
              <nldd-link key={fact.key} href={factHref(vacancy.id, fact)} text={fact.instruction} />
            ))}
          </Stack>
        </RouterLinks>
      )}
      {work.changed_facts.map((changed) => (
        <Quiet key={changed.key}>
          {changed.current
            ? `${changed.label}: in de vastgestelde tekst staat ${changed.settled}, de vacature heeft nu ${changed.current}.`
            : `${changed.label}: in de vastgestelde tekst staat ${changed.settled}, bij de vacature is dat nu niet ingevuld.`}
          {work.may_write ? ' Pas de tekst aan om dat over te nemen.' : ''}
        </Quiet>
      ))}
      {work.latest_changes.length > 0 && (
        <Quiet>
          Gewijzigd in versie {latest?.number}:{' '}
          {work.latest_changes.map((change) => change.summary).join(' ')}
        </Quiet>
      )}
      {error && <ErrorNotice message={error} />}
      {(step !== 'none' || others.length > 0) && (
        <nldd-button-group>
          {step !== 'none' && (
            <Button
              text={stepText}
              // The next step of the text that leads on this screen is the one
              // accent, unless the header of the vacancy already holds it.
              appearance={leading && !headerPrimary ? 'primary' : 'secondary'}
              loading={start.busy || settle.busy || withdraw.busy}
              onClick={act}
            />
          )}
          {others}
        </nldd-button-group>
      )}
      {work.remarks.length > 0 && (
        <Stack gap="group">
          <nldd-title size={6} text="Opmerkingen" heading-level={3} />
          {work.remarks.map((remark) => (
            <RemarkItem
              key={remark.id}
              vacancyId={vacancy.id}
              remark={remark}
              mayAct={work.may_remark}
              onAnswer={() => open({ kind: 'remark', text: work.kind, parent: remark })}
            />
          ))}
        </Stack>
      )}
      {(work.rounds.length > 0 || earlier.length > 0) && (
        <Stack gap="close">
          {work.rounds.map((item) => (
            <Quiet key={item.id}>{roundLine(item)}</Quiet>
          ))}
          {work.rounds
            .flatMap((item) => item.verdicts)
            .filter((verdict) => verdict.note)
            .map((verdict, index) => (
              <Quiet key={index}>
                {verdict.is_viewer ? 'Jij' : who(verdict.reviewer_name)}: {verdict.note}
              </Quiet>
            ))}
          {earlier.length > 0 && (
            <nldd-button-group>
              <Button
                text={
                  showAll ? 'Verberg eerdere versies' : `Toon eerdere versies (${earlier.length})`
                }
                size="sm"
                onClick={() => setShowAll(!showAll)}
              />
            </nldd-button-group>
          )}
          {showAll &&
            earlier.map((version) => (
              <Stack key={version.id} gap="close">
                <Quiet>
                  Versie {version.number} van {formatDate(version.created_at)}
                  {version.created_by_name ? `, ${version.created_by_name}` : ''}
                  {version.settled_at ? `, vastgesteld op ${formatDate(version.settled_at)}` : ''}
                </Quiet>
                <StructuredText text={version.text} headingLevel={4} />
              </Stack>
            ))}
        </Stack>
      )}
    </Section>
  );
}

function Publications({
  vacancyId,
  data,
  open,
  leading,
}: {
  vacancyId: string;
  data: VacancyTextWork;
  open: (sheet: Sheet) => void;
  leading: boolean;
}) {
  const remove = useWorkChange(vacancyId, (id: string) => removePublication(vacancyId, id));
  const { headerPrimary } = useVacancyShell();
  if (data.publications.length === 0 && !data.may_record_publication) return null;
  return (
    <Section title="Gepubliceerd">
      {data.publications.map((publication) => (
        <nldd-container key={publication.id} layout="row" gap="16" vertical-alignment="center">
          <nldd-text>
            Gepubliceerd op {publication.place_text} op {formatDate(publication.published_on)}
          </nldd-text>
          <ExternalLink href={publication.url} text="Bekijk de vacature" />
          {data.may_record_publication && (
            <Button
              text="Verwijder de link"
              size="sm"
              loading={remove.busy}
              onClick={() => remove.run(publication.id)}
            />
          )}
        </nldd-container>
      ))}
      {remove.error && <ErrorNotice message={remove.error} />}
      {data.may_record_publication && (
        <nldd-button-group>
          <Button
            text="Leg de link naar de vacature vast"
            appearance={
              leading && data.publication_missing && !headerPrimary ? 'primary' : 'secondary'
            }
            onClick={() => open({ kind: 'publication' })}
          />
        </nldd-button-group>
      )}
    </Section>
  );
}

/**
 * The texts of a vacancy as work: where each stands, who has it, the one
 * next step for this reader, the rounds and the remarks.
 */
export function TextWork({ vacancy }: { vacancy: Vacancy }) {
  const query = useQuery({
    queryKey: TEXT_WORK_KEY(vacancy.id),
    queryFn: () => fetchTextWork(vacancy.id),
  });
  const [sheet, setSheet] = useState<Sheet | null>(null);
  const [opened, setOpened] = useState(0);
  const want = useWorkChange(vacancy.id, () => wantVacancyText(vacancy.id));
  // Each text has its own course (schrijven, beoordelen, vaststellen), from
  // the same facts as its tasks.
  const parts = useCaseCourse('vacancy', vacancy.id).data?.parts ?? [];
  const whoseOf = (kind: TextKind) =>
    courseLine(parts.find((part) => part.subject === 'text' && part.subject_key === kind))?.who ||
    undefined;
  const navigate = useNavigate();
  // The head of the vacancy, a task or a link can ask to write one of the
  // texts: the vacancy text opens its page, the motivation its sheet.
  const [wanted, arrived] = useArrival('schrijf');
  const [handled, setHandled] = useState<string | null>(null);
  const asked = query.data?.texts.find((text) => text.kind === wanted && text.may_write);
  if (asked && asked.kind !== 'vacancy_text' && handled !== wanted) {
    const latest = asked.versions[asked.versions.length - 1];
    setHandled(wanted);
    setOpened((count) => count + 1);
    setSheet({
      kind: 'write',
      text: asked.kind,
      start: latest?.body ?? '',
      basedOn: latest?.id ?? null,
    });
  }
  const toPage = asked?.kind === 'vacancy_text';
  useEffect(() => {
    if (toPage) navigate(vacancyTextWritePath(vacancy.id), { replace: true });
    else if (wanted !== null && query.isSuccess) arrived();
  }, [toPage, wanted, query.isSuccess, arrived, navigate, vacancy.id]);
  if (query.isPending) return <Loading />;
  if (query.isError) return <LoadError error={query.error} retry={() => void query.refetch()} />;
  const data = query.data;
  const open = (next: Sheet) => {
    setOpened((count) => count + 1);
    setSheet(next);
  };
  const close = () => setSheet(null);
  const workOf = (kind: TextKind) => data.texts.find((text) => text.kind === kind);
  // One primary action on the screen: the first text that asks something of
  // this reader, and what waits on someone else never leads.
  const leadingKind = (
    data.texts.find((text) => !['none', 'withdraw', 'revise'].includes(text.action.key)) ??
    data.texts.find((text) => text.action.key === 'revise' && !data.publication_missing)
  )?.kind;
  const current = sheet && 'text' in sheet ? workOf(sheet.text) : undefined;

  return (
    <Stack gap="section">
      {data.texts.map((work) => (
        <TextBlock
          key={work.kind}
          vacancy={vacancy}
          work={work}
          data={data}
          open={open}
          leading={work.kind === leadingKind}
          whose={whoseOf(work.kind)}
        />
      ))}
      {data.vacancy_text_skipped && (
        <Section title={TEXT_KIND_LABELS.vacancy_text}>
          <Quiet>{NOT_OPENED}</Quiet>
          {want.error && <ErrorNotice message={want.error} />}
          {data.may_want_text && (
            <nldd-button-group>
              <Button
                text="Schrijf toch een vacaturetekst"
                loading={want.busy}
                onClick={() => want.run(undefined)}
              />
            </nldd-button-group>
          )}
        </Section>
      )}
      <Publications
        vacancyId={vacancy.id}
        data={data}
        open={open}
        leading={leadingKind === undefined}
      />
      {sheet?.kind === 'write' && current && (
        <WriteSheet
          key={opened}
          vacancyId={vacancy.id}
          sheet={sheet}
          work={current}
          onClose={close}
        />
      )}
      {sheet?.kind === 'offer' && current && (
        <OfferSheet
          key={opened}
          vacancyId={vacancy.id}
          kind={sheet.text}
          work={current}
          options={data.reviewer_options ?? []}
          onClose={close}
        />
      )}
      {sheet?.kind === 'judge' && (
        <JudgeSheet key={opened} vacancyId={vacancy.id} sheet={sheet} onClose={close} />
      )}
      {sheet?.kind === 'tailored' && (
        <TailoredSheet
          key={opened}
          vacancyId={vacancy.id}
          note={data.drafting_note}
          onClose={close}
        />
      )}
      {sheet?.kind === 'remark' && current && (
        <RemarkSheet
          key={opened}
          vacancyId={vacancy.id}
          sheet={sheet}
          work={current}
          onClose={close}
        />
      )}
      {sheet?.kind === 'publication' && (
        <PublicationSheet key={opened} vacancy={vacancy} onClose={close} />
      )}
    </Stack>
  );
}

/** In the header of a vacancy: where anyone can read the published vacancy. */
export function PublishedLinks({ vacancyId }: { vacancyId: string }) {
  // Not everyone who sees a vacancy may read its text work; then no link.
  const query = useQuery({
    queryKey: TEXT_WORK_KEY(vacancyId),
    queryFn: () => fetchTextWork(vacancyId),
    retry: false,
  });
  const publications = query.data?.publications ?? [];
  if (publications.length === 0) return null;
  return (
    <nldd-container layout="row" gap="16" vertical-alignment="center">
      {publications.map((publication) => (
        <ExternalLink
          key={publication.id}
          href={publication.url}
          text={`Bekijk de vacature op ${publication.place_text}`}
        />
      ))}
    </nldd-container>
  );
}
