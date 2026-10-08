import { useState } from 'react';
import { formatDate } from '@/lib/format';
import {
  addText,
  draftText,
  establishText,
  type TextKind,
  type TextVersion,
  type Vacancy,
  type VacancyOptions,
} from './api';
import { useVacancyChange } from './hooks';
import { TEXT_KIND_LABELS, originOf } from './labels';
import { Button, ErrorNotice, FormSheet, Note, Paragraphs, SectionHeading, TextInput } from './ui';

const KINDS: TextKind[] = ['vacancy_text', 'motivation'];

const KIND_HELP: Record<TextKind, string> = {
  vacancy_text:
    'De tekst waarmee de vacature wordt opengesteld. Alleen een vastgestelde versie gaat grip uit.',
  motivation:
    'Waarom de vacature nodig is. De vastgestelde versie komt op het aanvraagformulier.',
};

function versionState(version: TextVersion): string {
  if (version.is_current) return 'Vastgesteld, de geldende versie';
  if (version.established_at) return `Eerder vastgesteld op ${formatDate(version.established_at)}`;
  return version.source === 'model' ? 'Concept van het taalmodel, niet vastgesteld' : 'Concept, niet vastgesteld';
}

function people(version: TextVersion): string | null {
  const parts = [];
  if (version.created_by_name) {
    parts.push(
      version.source === 'model'
        ? `Aangevraagd door ${version.created_by_name}`
        : `Geschreven door ${version.created_by_name}`,
    );
  }
  if (version.established_by_name) parts.push(`vastgesteld door ${version.established_by_name}`);
  return parts.length > 0 ? `${parts.join(', ')}.` : null;
}

interface VersionProps {
  vacancy: Vacancy;
  version: TextVersion;
  onRewrite: (version: TextVersion) => void;
}

function Version({ vacancy, version, onRewrite }: VersionProps) {
  const establish = useVacancyChange(vacancy.id, () => establishText(vacancy.id, version.id));
  const who = people(version);
  return (
    <article>
      <nldd-tag
        color={version.is_current ? 'success' : version.source === 'model' ? 'warning' : 'neutral'}
        text={versionState(version)}
      />
      <nldd-spacer size="8" />
      <Paragraphs text={version.body} />
      <nldd-spacer size="8" />
      <Note>
        {originOf(version)}.{who ? ` ${who}` : ''}
      </Note>
      {establish.error && <ErrorNotice message={establish.error} />}
      {vacancy.permissions.can_edit && (
        <>
          <nldd-spacer size="8" />
          <nldd-button-group>
            {!version.established_at && (
              <Button
                text="Stel vast"
                size="sm"
                loading={establish.busy}
                accessibleLabel={`Stel deze versie van de ${TEXT_KIND_LABELS[version.kind].toLowerCase()} vast`}
                onClick={() => establish.run(undefined)}
              />
            )}
            <Button
              text="Herschrijf"
              size="sm"
              appearance="neutral-transparent"
              accessibleLabel={`Herschrijf deze versie van de ${TEXT_KIND_LABELS[version.kind].toLowerCase()}`}
              onClick={() => onRewrite(version)}
            />
          </nldd-button-group>
        </>
      )}
      <nldd-spacer size="16" />
    </article>
  );
}

interface WriteState {
  kind: TextKind;
  basedOn: TextVersion | null;
}

function WriteSheet({
  vacancy,
  state,
  open,
  onClose,
}: {
  vacancy: Vacancy;
  state: WriteState;
  open: boolean;
  onClose: () => void;
}) {
  const [body, setBody] = useState(state.basedOn?.body ?? '');
  const [problem, setProblem] = useState<string | null>(null);
  const change = useVacancyChange(
    vacancy.id,
    (text: string) => addText(vacancy.id, state.kind, text, state.basedOn?.id),
    onClose,
  );
  const label = TEXT_KIND_LABELS[state.kind];

  function submit() {
    setProblem(null);
    if (!body.trim()) return setProblem('De tekst is leeg.');
    change.run(body.trim());
  }

  return (
    <FormSheet
      open={open}
      title={state.basedOn ? `${label} herschrijven` : `${label} schrijven`}
      submitText="Bewaar als nieuwe versie"
      onSubmit={submit}
      onClose={onClose}
      busy={change.busy}
      error={problem ?? change.error}
    >
      <Note>
        Een versie verandert niet meer: wat je bewaart wordt een nieuwe versie.
        {state.basedOn?.model_assisted
          ? ' Omdat je uitgaat van een concept van het taalmodel, blijft dat bij de nieuwe versie vermeld.'
          : ''}{' '}
        Vaststellen doe je daarna apart.
      </Note>
      <TextInput label={label} value={body} onChange={setBody} multiline required />
    </FormSheet>
  );
}

function DraftSheet({
  vacancy,
  kind,
  open,
  onClose,
}: {
  vacancy: Vacancy;
  kind: TextKind;
  open: boolean;
  onClose: () => void;
}) {
  const [summary, setSummary] = useState('');
  const change = useVacancyChange(
    vacancy.id,
    (text: string) => draftText(vacancy.id, kind, text.trim() || undefined),
    onClose,
  );
  const label = TEXT_KIND_LABELS[kind].toLowerCase();

  return (
    <FormSheet
      open={open}
      title={`Concept van de ${label} laten opstellen`}
      submitText="Stel concept op"
      onSubmit={() => change.run(summary)}
      onClose={onClose}
      busy={change.busy}
      error={change.error}
    >
      <Note>
        Het taalmodel krijgt de functie, de schaal, het aantal fte, de periode, het type contract
        en de naam van de opdracht. Er gaan geen namen van personen naar het model. Het resultaat
        is een concept: een mens leest het, past het aan en stelt het vast.
      </Note>
      <TextInput
        label="Samenvatting van de opdracht"
        hint="Alleen wat je hier typt gaat mee naar het model. Noem geen personen."
        value={summary}
        onChange={setSummary}
        multiline
        optional
      />
    </FormSheet>
  );
}

/** The texts of a vacancy: every version with its origin, writing, drafting, establishing. */
export function TextsSection({
  vacancy,
  options,
}: {
  vacancy: Vacancy;
  options: VacancyOptions | undefined;
}) {
  const [write, setWrite] = useState<WriteState>({ kind: 'vacancy_text', basedOn: null });
  const [writing, setWriting] = useState(false);
  const [draftKind, setDraftKind] = useState<TextKind>('vacancy_text');
  const [drafting, setDrafting] = useState(false);
  const canEdit = vacancy.permissions.can_edit;
  const draftingAvailable = options?.drafting_available ?? false;

  function startWriting(kind: TextKind, basedOn: TextVersion | null) {
    setWrite({ kind, basedOn });
    setWriting(true);
  }

  return (
    <>
      <SectionHeading text="Teksten" />
      {canEdit && !draftingAvailable && options !== undefined && (
        <Note>
          Het taalmodel is in deze instantie niet ingesteld. Een concept laten opstellen kan pas
          als de beheerder dat heeft gedaan; zelf schrijven kan altijd.
        </Note>
      )}
      {KINDS.map((kind) => {
        // Newest first: the version to act on is on top.
        const versions = vacancy.texts.filter((text) => text.kind === kind).reverse();
        return (
          <section key={kind}>
            <nldd-spacer size="16" />
            <SectionHeading text={TEXT_KIND_LABELS[kind]} level={3} />
            <Note>{KIND_HELP[kind]}</Note>
            <nldd-spacer size="8" />
            {versions.length === 0 && <Note>Er is nog geen tekst.</Note>}
            {versions.map((version) => (
              <Version
                key={version.id}
                vacancy={vacancy}
                version={version}
                onRewrite={(base) => startWriting(kind, base)}
              />
            ))}
            {canEdit && (
              <nldd-button-group>
                <Button text="Schrijf zelf" onClick={() => startWriting(kind, null)} />
                <Button
                  text="Laat een concept opstellen"
                  disabled={!draftingAvailable}
                  onClick={() => {
                    setDraftKind(kind);
                    setDrafting(true);
                  }}
                />
              </nldd-button-group>
            )}
          </section>
        );
      })}
      {canEdit && (
        <>
          <WriteSheet
            key={`write-${write.kind}-${write.basedOn?.id ?? 'new'}-${vacancy.texts.length}`}
            vacancy={vacancy}
            state={write}
            open={writing}
            onClose={() => setWriting(false)}
          />
          <DraftSheet
            key={`draft-${draftKind}-${vacancy.texts.length}`}
            vacancy={vacancy}
            kind={draftKind}
            open={drafting}
            onClose={() => setDrafting(false)}
          />
        </>
      )}
    </>
  );
}
