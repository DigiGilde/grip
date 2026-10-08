import { useState, type ReactNode } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, errorMessage } from '@/api/client';
import { formatDate } from '@/lib/format';
import { ExternalLink } from '@/ui/Icon';
import { ErrorNotice, FormSheet, Loading, Quiet, Section, Stack } from '@/ui/layout';
import { VACANCY_KEYS, type TextKind, type Vacancy } from './api';
import { todayIso } from './hooks';
import { TEXT_KIND_LABELS } from './labels';
import { StructuredText } from './StructuredText';
import {
  TEXT_WORK_KEY,
  addRemark,
  draftTailored,
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
  withdrawReview,
  type Publication,
  type Remark,
  type Round,
  type TextWork as Work,
  type VacancyTextWork,
} from './textWorkApi';
import { Button, CheckboxInput, DateInput, SelectInput, TextInput } from './ui';

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
      <TextInput
        label={label}
        hint="Een kop schrijf je als een regel die begint met ##, een lijst met een streepje per regel."
        value={body}
        onChange={setBody}
        multiline
        required
      />
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

function TailoredSheet({
  vacancyId,
  note,
  onClose,
}: {
  vacancyId: string;
  note: string | null | undefined;
  onClose: () => void;
}) {
  const [instruction, setInstruction] = useState('');
  const change = useWorkChange(vacancyId, () => draftTailored(vacancyId, instruction), onClose);
  return (
    <FormSheet
      open
      title="Stel een tekst op maat op"
      submitText={change.busy ? 'Het concept wordt geschreven' : 'Stel een concept op'}
      onSubmit={() => change.run(undefined)}
      onClose={onClose}
      busy={change.busy}
      error={change.error}
    >
      <TextInput
        label="Wat is bijzonder aan deze vacature"
        hint="Bijvoorbeeld wat het team maakt en waar de nadruk op ligt. Noem geen personen."
        value={instruction}
        onChange={setInstruction}
        multiline
        optional
      />
      <Quiet>
        {change.busy
          ? 'Dit duurt ongeveer een halve minuut.'
          : 'Het concept volgt de standaardtekst van de rol. Je leest het, past het aan en stelt het vast.'}
        {note ? ` ${note}` : ''}
      </Quiet>
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
  const sections = latest ? splitSections(latest.body).filter((section) => section.heading) : [];
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

function PublicationSheet({ vacancyId, onClose }: { vacancyId: string; onClose: () => void }) {
  const [place, setPlace] = useState<Publication['place']>('government_wide');
  const [url, setUrl] = useState('');
  const [day, setDay] = useState(todayIso());
  const [problem, setProblem] = useState<string | null>(null);
  const change = useWorkChange(
    vacancyId,
    () => setPublication(vacancyId, place, url.trim(), day),
    onClose,
  );
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
      error={problem ?? change.error}
    >
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
          <Button text="Antwoord" size="sm" appearance="neutral-transparent" onClick={onAnswer} />
          <Button
            text={remark.resolved_at ? 'Zet weer open' : 'Markeer als afgehandeld'}
            size="sm"
            appearance="neutral-transparent"
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
}: {
  vacancy: Vacancy;
  work: Work;
  data: VacancyTextWork;
  open: (sheet: Sheet) => void;
  /**
   * The one text on the screen whose next step leads. The page header holds
   * the primary action of the vacancy, so the step leads as a secondary
   * button; only a reviewer, who has no action in the header, gets a primary.
   */
  leading: boolean;
}) {
  const [showAll, setShowAll] = useState(false);
  const latest = work.versions[work.versions.length - 1];
  const settled = [...work.versions].reverse().find((version) => version.settled_at);
  const start = useWorkChange(vacancy.id, () => startFromStandardText(vacancy.id));
  const settle = useWorkChange(vacancy.id, (id: string) => settleVersion(vacancy.id, id));
  const withdraw = useWorkChange(vacancy.id, (id: string) => withdrawReview(vacancy.id, id));
  const round = work.rounds[work.rounds.length - 1];
  const label = TEXT_KIND_LABELS[work.kind];
  const isVacancyText = work.kind === 'vacancy_text';
  const standard = work.standard_text;

  function act() {
    const key = work.action.key;
    if (key === 'start') start.run(undefined);
    else if (key === 'write') open({ kind: 'write', text: work.kind, start: '', basedOn: null });
    else if (key === 'process' || key === 'revise') {
      open({
        kind: 'write',
        text: work.kind,
        start: latest?.body ?? '',
        basedOn: latest?.id ?? null,
      });
    } else if (key === 'offer') open({ kind: 'offer', text: work.kind });
    else if (key === 'withdraw' && round) withdraw.run(round.id);
    else if (key === 'judge' && work.viewer_review_id) {
      open({ kind: 'judge', text: work.kind, reviewId: work.viewer_review_id });
    } else if (key === 'settle' && latest) settle.run(latest.id);
  }

  const secondary: ReactNode[] = [];
  const primary = work.action.key;
  if (work.may_write && latest && !['process', 'revise'].includes(primary)) {
    secondary.push(
      <Button
        key="write"
        text="Schrijf verder"
        appearance="neutral-transparent"
        onClick={() =>
          open({ kind: 'write', text: work.kind, start: latest.body, basedOn: latest.id })
        }
      />,
    );
  }
  if (work.may_write && !latest && primary !== 'write') {
    secondary.push(
      <Button
        key="own"
        text="Schrijf zelf"
        appearance="neutral-transparent"
        onClick={() => open({ kind: 'write', text: work.kind, start: '', basedOn: null })}
      />,
    );
  }
  if (isVacancyText && work.may_write && standard && data.drafting_available) {
    secondary.push(
      <Button
        key="tailored"
        text="Stel een tekst op maat op"
        appearance="neutral-transparent"
        onClick={() => open({ kind: 'tailored' })}
      />,
    );
  }
  if (work.may_settle && latest && primary !== 'settle') {
    secondary.push(
      <Button
        key="settle"
        text="Stel vast"
        appearance="neutral-transparent"
        loading={settle.busy}
        onClick={() => settle.run(latest.id)}
      />,
    );
  }
  if (work.may_remark && latest) {
    secondary.push(
      <Button
        key="remark"
        text="Plaats een opmerking"
        appearance="neutral-transparent"
        onClick={() => open({ kind: 'remark', text: work.kind })}
      />,
    );
  }

  const error = start.error ?? settle.error ?? withdraw.error;
  const earlier = work.versions.slice(0, -1).reverse();
  return (
    <Section title={label}>
      <nldd-container layout="row" gap="8" vertical-alignment="center">
        <nldd-tag color={STATE_COLORS[work.state]} text={work.state_text} />
        {work.with_whom && <Quiet>{work.with_whom}</Quiet>}
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
      {!work.needed && (
        <Quiet>Deze vacature wordt niet opengesteld en heeft geen vacaturetekst nodig.</Quiet>
      )}
      {work.state === 'none' && isVacancyText && standard && (
        <Quiet>
          {standard.match === 'function_group'
            ? `Voor deze rol is geen standaardtekst. De tekst van ${standard.role} lijkt er het meest op.`
            : `Er is een standaardtekst voor ${standard.role}.`}
          {standard.unread ? ' Die tekst is afgeleid en nog niet nagelezen.' : ''}
        </Quiet>
      )}
      {latest && <StructuredText text={latest.body} />}
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
        <Quiet>Nog in te vullen voor je kunt vaststellen: {work.open_passages.join(', ')}</Quiet>
      )}
      {work.latest_changes.length > 0 && (
        <Quiet>
          Gewijzigd in versie {latest?.number}:{' '}
          {work.latest_changes.map((change) => change.summary).join(' ')}
        </Quiet>
      )}
      {error && <ErrorNotice message={error} />}
      {(work.action.key !== 'none' || secondary.length > 0) && (
        <nldd-button-group>
          {work.action.key !== 'none' && (
            <Button
              text={work.action.text}
              // The next step of a text is its one filled button; what else
              // can be done with it stays quiet beside it.
              appearance={leading && work.action.key === 'judge' ? 'primary' : 'secondary'}
              loading={start.busy || settle.busy || withdraw.busy}
              onClick={act}
            />
          )}
          {secondary}
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
                appearance="neutral-transparent"
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
                <StructuredText text={version.body} headingLevel={4} />
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
              appearance="neutral-transparent"
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
            appearance={leading && data.publication_missing ? 'secondary' : 'neutral-transparent'}
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
  if (query.isPending) return <Loading />;
  if (query.isError) return <ErrorNotice message={errorMessage(query.error)} />;
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
        />
      ))}
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
        <PublicationSheet key={opened} vacancyId={vacancy.id} onClose={close} />
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
