import { useRef, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { errorMessage } from '@/api/client';
import { Button, TextInput } from '@/features/assignments/ui';
import { ErrorNotice, FormSheet, Quiet, Stack } from '@/ui/layout';
import { QUOTE_SECTION_MARKS } from '@/ui/text/marks';
import { TextEditor, type TextEditorHandle } from '@/ui/TextEditor';
import {
  conflictOf,
  draftSection,
  dropLocal,
  keepLocal,
  readLocal,
  rewritePassage,
  saveSection,
  type DraftConflict,
  type DraftSection,
  type QuoteDraft,
} from './draftApi';
import { formatDateTime } from './format';
import { Prose } from './Prose';
import './register';

interface SectionEditorProps {
  assignmentId: string;
  section: DraftSection;
  /** A language model can be asked, and the organisation opened this section for it. */
  mayDraft: boolean;
  /** The draft as the server has it after a save or a model draft. */
  onChanged: (draft: QuoteDraft) => void;
  /** A person saved the text: the page moves on to what is next. */
  onSaved?: (draft: QuoteDraft) => void;
}

/**
 * Writing one section. The text is saved by the person, on purpose: saving
 * is what makes a text count, also one a language model proposed. Until the
 * server confirms, a copy stays in this browser, so nothing typed is lost.
 * Each save names the version it started from; when a colleague saved in
 * between, the server refuses, the person sees their text and chooses, and
 * nothing is overwritten unseen.
 */
export function SectionEditor({
  assignmentId,
  section,
  mayDraft,
  onChanged,
  onSaved,
}: SectionEditorProps) {
  const [local] = useState(() => readLocal(assignmentId, section.key));
  const restored = local !== null && local.text !== section.body;
  const [text, setText] = useState(restored ? local.text : section.body);
  // What the server had when this text was started from.
  const [base, setBase] = useState(restored ? local.base : section.body);
  const [theirs, setTheirs] = useState<
    (DraftConflict & { body: string; version: number | undefined }) | null
  >(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<string | null>(null);

  const editor = useRef<TextEditorHandle>(null);
  const typed = (next: string) => {
    setText(next);
    setSavedAt(null);
    keepLocal(assignmentId, section.key, { text: next, base, at: new Date().toISOString() });
  };

  const settle = (draft: QuoteDraft) => {
    const now = draft.sections.find((item) => item.key === section.key);
    dropLocal(assignmentId, section.key);
    setBase(now?.body ?? '');
    setText(now?.body ?? '');
    setVersion(now?.version);
    setTheirs(null);
    setProblem(null);
    onChanged(draft);
  };

  // The version this text was started from. The server refuses a save on an
  // older one, and says who saved in between and what stands there now.
  const [version, setVersion] = useState(section.version);
  const save = useMutation({
    mutationFn: (onTopOf: number | undefined) =>
      saveSection(assignmentId, section.key, {
        body: text,
        // Writing a section that was left out puts it in the quote: nobody
        // writes a text to leave it out.
        ...(section.included || !text.trim() ? {} : { included: true }),
        ...(onTopOf === undefined ? {} : { version: onTopOf }),
      }),
    onSuccess: (draft) => {
      settle(draft);
      setSavedAt(new Date().toISOString());
      onSaved?.(draft);
    },
    onError: (failure) => {
      const conflict = conflictOf(failure);
      const now = conflict?.current.sections.find((item) => item.key === section.key);
      if (!conflict || !now) {
        setProblem(errorMessage(failure));
        return;
      }
      // Nothing was saved and nothing is lost: the typed text stays in the
      // field and in this browser until the person chooses.
      setProblem(null);
      setTheirs({ ...conflict, body: now.body, version: now.version });
    },
  });

  const propose = useMutation({
    mutationFn: () => draftSection(assignmentId, section.key),
    onSuccess: settle,
    onError: (failure) => setProblem(errorMessage(failure)),
  });

  // --- rewriting a selected passage ---
  const [passage, setPassage] = useState<{ start: number; end: number; text: string } | null>(null);
  const [instruction, setInstruction] = useState('');
  const [proposal, setProposal] = useState<string | null>(null);
  const [rewriteError, setRewriteError] = useState<string | null>(null);
  const rewrite = useMutation({
    mutationFn: () =>
      rewritePassage(assignmentId, section.key, {
        passage: passage?.text ?? '',
        instruction: instruction.trim() || null,
      }),
    onSuccess: (result) => setProposal(result.text),
    onError: (failure) => setRewriteError(errorMessage(failure)),
  });
  const startRewrite = () => {
    const picked = editor.current?.selection();
    const start = picked?.start ?? 0;
    const end = picked?.end ?? 0;
    if (end <= start) {
      setProblem('Selecteer eerst de passage die je wilt laten herschrijven.');
      return;
    }
    setProblem(null);
    setRewriteError(null);
    setProposal(null);
    setInstruction('');
    setPassage({ start, end, text: text.slice(start, end) });
  };
  const takeProposal = () => {
    if (!passage || proposal === null) return;
    const next = text.slice(0, passage.start) + proposal + text.slice(passage.end);
    setText(next);
    setSavedAt(null);
    keepLocal(assignmentId, section.key, { text: next, base, at: new Date().toISOString() });
    setPassage(null);
  };

  const dirty = text !== section.body;
  const unsettled = !section.settled;
  const emptyForModel = !section.body || section.origin === 'generated';

  return (
    <Stack gap="related">
      {section.hint ? <Quiet>{section.hint}</Quiet> : null}
      {restored && dirty ? (
        <Quiet>
          Je tekst van {formatDateTime(local.at)} was nog niet bewaard en staat hier weer.
        </Quiet>
      ) : null}
      {unsettled ? (
        <nldd-text data-proposal>
          Dit is een voorstel van het taalmodel. Lees het na, pas het aan en bewaar het: pas dan
          telt het mee.
        </nldd-text>
      ) : null}
      {unsettled && section.generated?.context === 'unreachable' ? (
        <Quiet>Opgesteld zonder de context uit het corpus: dat was niet bereikbaar.</Quiet>
      ) : null}
      <TextEditor
        ref={editor}
        label={`Tekst van ${section.heading}`}
        value={text}
        onChange={typed}
        marks={QUOTE_SECTION_MARKS}
        rows={10}
        disabled={propose.isPending}
      />
      {theirs !== null ? (
        <Stack gap="related">
          <nldd-banner
            variant="warning"
            size="sm"
            text={`${theirs.changedBy ?? 'Een collega'} heeft dit onderdeel intussen gewijzigd`}
            supporting-text={`${
              theirs.changedAt ? `Op ${formatDateTime(theirs.changedAt)}. ` : ''
            }Er is niets overschreven en je eigen tekst staat nog in het veld. Kies welke tekst blijft.`}
          />
          <Stack gap="close">
            <Quiet>De tekst die er nu staat</Quiet>
            <div data-their-text>
              {theirs.body ? <Prose text={theirs.body} /> : <Quiet>Geen tekst.</Quiet>}
            </div>
          </Stack>
          <nldd-button-group>
            <Button
              text="Bewaar mijn tekst"
              loading={save.isPending}
              onClick={() => save.mutate(theirs.version)}
            />
            <Button
              text="Neem de andere tekst over"
              onClick={() => {
                dropLocal(assignmentId, section.key);
                setText(theirs.body);
                setBase(theirs.body);
                setVersion(theirs.version);
                onChanged(theirs.current);
                setTheirs(null);
              }}
            />
          </nldd-button-group>
        </Stack>
      ) : null}
      {problem ? <ErrorNotice message={problem} /> : null}
      {theirs === null ? (
        <nldd-container layout="wrap" gap="8" vertical-alignment="center">
          <Button
            text={unsettled && !dirty ? 'Stel vast' : 'Bewaar'}
            loading={save.isPending}
            disabled={propose.isPending}
            onClick={() => save.mutate(version)}
          />
          {mayDraft && emptyForModel ? (
            <Button
              text={section.body ? 'Stel een nieuw concept op' : 'Stel een concept op'}
              loading={propose.isPending}
              disabled={save.isPending}
              onClick={() => {
                setProblem(null);
                propose.mutate();
              }}
            />
          ) : null}
          {mayDraft && text ? (
            <Button
              text="Herschrijf selectie"
              disabled={propose.isPending}
              onClick={startRewrite}
            />
          ) : null}
          {propose.isPending ? (
            <Quiet>Het taalmodel schrijft. Dat kan een halve minuut duren.</Quiet>
          ) : savedAt ? (
            <Quiet>Bewaard om {formatDateTime(savedAt).split(', ').pop()}</Quiet>
          ) : dirty ? (
            <Quiet>Nog niet bewaard</Quiet>
          ) : null}
        </nldd-container>
      ) : null}

      <FormSheet
        open={passage !== null}
        title="Passage herschrijven"
        submitText={proposal === null ? 'Herschrijf' : 'Neem over'}
        busy={rewrite.isPending}
        error={rewriteError}
        onClose={() => setPassage(null)}
        onSubmit={() => {
          setRewriteError(null);
          if (proposal === null) rewrite.mutate();
          else takeProposal();
        }}
      >
        <Stack gap="close">
          <Quiet>De passage die je selecteerde</Quiet>
          <nldd-text>{passage?.text}</nldd-text>
        </Stack>
        {proposal === null ? (
          <>
            <TextInput
              label="Wat moet er anders"
              hint="Bijvoorbeeld: korter, of zonder vakjargon."
              value={instruction}
              onChange={setInstruction}
              optional
            />
            {rewrite.isPending ? (
              <Quiet>Het taalmodel schrijft. Dat kan een halve minuut duren.</Quiet>
            ) : null}
          </>
        ) : (
          <Stack gap="close">
            <Quiet>Voorstel van het taalmodel</Quiet>
            <nldd-text data-rewrite-proposal>{proposal}</nldd-text>
            <Quiet>
              Overnemen zet het voorstel in je tekst. Het telt pas mee als je het onderdeel bewaart.
            </Quiet>
          </Stack>
        )}
      </FormSheet>
    </Stack>
  );
}
