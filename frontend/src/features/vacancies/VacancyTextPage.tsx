/**
 * Writing the vacancy text: a page of its own, because a text of a page or
 * more is not written in a side panel. The whole text in one editor, on a
 * measure that reads; what a standard text left open is counted and one step
 * away. Saving makes a new version and leads back to the Tekst tab, where the
 * text is offered for review and settled.
 */
import { useEffect, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import { ApiError, errorMessage } from '@/api/client';
import { useInstance } from '@/layout/useInstance';
import { useRouterLinks } from '@/layout/useRouterLinks';
import { formatDate } from '@/lib/format';
import { Button } from '@/ui/Button';
import {
  ErrorNotice,
  LoadError,
  Loading,
  Page,
  Quiet,
  Section,
  Stack,
  NoAccess,
  StateNotice,
} from '@/ui/layout';
import { RichText } from '@/ui/RichText';
import { openPlaces, VACANCY_TEXT_MARKS } from '@/ui/text/marks';
import { TextEditor, type TextEditorHandle } from '@/ui/TextEditor';
import { VACANCY_KEYS, fetchVacancy } from './api';
import { vacancyTabPath } from './paths';
import { TailoredSheet } from './TailoredSheet';
import {
  TEXT_WORK_KEY,
  fetchTextWork,
  saveVersion,
  useStandardText as startFromStandardText,
  type VacancyTextWork,
} from './textWorkApi';

const KIND = 'vacancy_text' as const;

/** What was typed and not yet saved, kept in this browser until the server has it. */
const safeKey = (vacancyId: string) => `grip.vacaturetekst.${vacancyId}`;

function readSafe(vacancyId: string): { body: string; basedOn: string | null } | null {
  try {
    const raw = window.localStorage.getItem(safeKey(vacancyId));
    return raw ? (JSON.parse(raw) as { body: string; basedOn: string | null }) : null;
  } catch {
    return null;
  }
}

function writeSafe(vacancyId: string, value: { body: string; basedOn: string | null } | null) {
  try {
    if (value) window.localStorage.setItem(safeKey(vacancyId), JSON.stringify(value));
    else window.localStorage.removeItem(safeKey(vacancyId));
  } catch {
    // Without storage the text is only in the field; saving still works.
  }
}

function OpenPlaceItem({ text, onGo }: { text: string; onGo: () => void }) {
  const ref = useRef<HTMLElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.addEventListener('click', onGo);
    return () => el.removeEventListener('click', onGo);
  });
  return (
    <nldd-list-item ref={ref} size="sm" button accessible-label={`Ga naar: ${text}`}>
      <nldd-text-cell text={text} />
    </nldd-list-item>
  );
}

export function VacancyTextPage() {
  const { vacancyId = '' } = useParams();
  const instance = useInstance();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const root = useRef<HTMLDivElement>(null);
  useRouterLinks(root);
  const editor = useRef<TextEditorHandle>(null);
  const back = vacancyTabPath(vacancyId, 'text');

  const vacancy = useQuery({
    queryKey: VACANCY_KEYS.detail(vacancyId),
    queryFn: () => fetchVacancy(vacancyId),
    enabled: vacancyId !== '',
    retry: false,
  });
  const work = useQuery({
    queryKey: TEXT_WORK_KEY(vacancyId),
    queryFn: () => fetchTextWork(vacancyId),
    enabled: vacancyId !== '',
    retry: false,
  });
  const text = work.data?.texts.find((item) => item.kind === KIND);
  const latest = text?.versions[text.versions.length - 1];

  // The text starts from the latest version, or from what was typed here
  // before and never reached the server.
  const [body, setBody] = useState<string | null>(null);
  const [basedOn, setBasedOn] = useState<string | null>(null);
  const [restored, setRestored] = useState(false);
  const [listOpen, setListOpen] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  if (body === null && work.data) {
    const kept = readSafe(vacancyId);
    const start = latest?.body ?? '';
    if (kept && kept.body.trim() && kept.body !== start) {
      setBody(kept.body);
      setBasedOn(kept.basedOn);
      setRestored(true);
    } else {
      setBody(start);
      setBasedOn(latest?.id ?? null);
    }
  }

  const save = useMutation({
    mutationFn: (input: { body: string; basedOn: string | null }) =>
      saveVersion(vacancyId, KIND, input.body, input.basedOn),
    onSuccess: (saved) => {
      writeSafe(vacancyId, null);
      queryClient.setQueryData(TEXT_WORK_KEY(vacancyId), saved);
      void queryClient.invalidateQueries({ queryKey: VACANCY_KEYS.detail(vacancyId) });
      void queryClient.invalidateQueries({ queryKey: ['tasks'] });
      navigate(back);
    },
    onError: (error) => {
      // Someone else saved in between: fetch their version to show beside this one.
      if (error instanceof ApiError && error.status === 409) {
        void queryClient.invalidateQueries({ queryKey: TEXT_WORK_KEY(vacancyId) });
      }
    },
  });
  // An empty text is not started in an empty field when there is something
  // to start from: the standard text of the role, or a draft that fits.
  const [ownStart, setOwnStart] = useState(false);
  const [tailoring, setTailoring] = useState(false);
  const takeOver = (next: VacancyTextWork) => {
    const fresh = next.texts.find((item) => item.kind === KIND);
    const version = fresh?.versions[fresh.versions.length - 1];
    setBody(version?.body ?? '');
    setBasedOn(version?.id ?? null);
  };
  const start = useMutation({
    mutationFn: () => startFromStandardText(vacancyId),
    onSuccess: (next) => {
      queryClient.setQueryData(TEXT_WORK_KEY(vacancyId), next);
      void queryClient.invalidateQueries({ queryKey: ['tasks'] });
      takeOver(next);
    },
  });
  const standard = text?.standard_text;
  const choosing =
    Boolean(standard) && !latest && !restored && !ownStart && body !== null && !body.trim();
  const conflict = save.error instanceof ApiError && save.error.status === 409;
  const moved = conflict && latest !== undefined && latest.id !== basedOn;

  const places = body ? openPlaces(body) : [];
  const denied = work.error instanceof ApiError && [403, 404].includes(work.error.status);
  const title = vacancy.data
    ? `Vacaturetekst voor ${vacancy.data.function_title}`
    : 'Vacaturetekst';

  return (
    <div ref={root}>
      <Page
        title={title}
        instanceName={instance?.name}
        width="760px"
        back={{ href: back, text: 'Terug naar de vacature' }}
      >
        {work.isPending && <Loading />}
        {denied && (
          <StateNotice
            state="not-found"
            text="Deze tekst staat niet voor je klaar"
            detail="De vacature bestaat niet, of je schrijft niet aan haar tekst."
          />
        )}
        {work.isError && !denied && (
          <LoadError error={work.error} retry={() => void work.refetch()} />
        )}
        {text && !text.may_write && (
          <NoAccess who="De tekst wijzigen kan wie de vacature beheert of er als schrijver bij is betrokken." />
        )}
        {text && text.may_write && choosing && standard && (
          <Stack gap="group">
            <nldd-text>
              {standard.match === 'function_group'
                ? `Voor deze rol is geen standaardtekst. De tekst van ${standard.role} lijkt er het meest op.`
                : `Er is een standaardtekst voor ${standard.role}.`}
              {standard.unread ? ' Die tekst is afgeleid en nog niet nagelezen.' : ''}
            </nldd-text>
            {start.isError && <ErrorNotice message={errorMessage(start.error)} />}
            <nldd-button-group>
              <Button
                appearance="primary"
                text="Begin met de standaardtekst"
                loading={start.isPending}
                onClick={() => start.mutate()}
              />
              {work.data?.drafting_available && (
                <Button text="Stel een tekst op maat op" onClick={() => setTailoring(true)} />
              )}
              <Button text="Schrijf zelf" onClick={() => setOwnStart(true)} />
            </nldd-button-group>
            {tailoring && (
              <TailoredSheet
                vacancyId={vacancyId}
                note={work.data?.drafting_note}
                onClose={() => setTailoring(false)}
                onDrafted={takeOver}
              />
            )}
          </Stack>
        )}
        {text && text.may_write && body !== null && !choosing && (
          <>
            {restored && (
              <Quiet>
                Dit is wat je eerder schreef en nog niet had bewaard
                {latest
                  ? `; de laatst bewaarde versie is van ${formatDate(latest.created_at)}`
                  : ''}
                .
              </Quiet>
            )}
            <TextEditor
              ref={editor}
              label="Vacaturetekst"
              value={body}
              onChange={(next) => {
                setBody(next);
                writeSafe(vacancyId, { body: next, basedOn });
              }}
              marks={VACANCY_TEXT_MARKS}
              rows={24}
              showOpenPlaces
              required
            />
            {places.length > 0 && (
              <Stack gap="close">
                <nldd-button-group>
                  <Button
                    size="sm"
                    text={
                      listOpen
                        ? 'Verberg wat nog open staat'
                        : `Toon wat nog open staat (${places.length})`
                    }
                    onClick={() => setListOpen(!listOpen)}
                  />
                </nldd-button-group>
                {listOpen && (
                  <nldd-list accessible-label="Nog in te vullen">
                    {places.map((place, index) => (
                      <OpenPlaceItem
                        key={`${place.start}-${place.what}`}
                        text={place.what}
                        onGo={() => editor.current?.goToOpenPlace(index)}
                      />
                    ))}
                  </nldd-list>
                )}
              </Stack>
            )}
            {(problem ?? (save.isError && !moved)) && (
              <ErrorNotice message={problem ?? errorMessage(save.error)} />
            )}
            {moved && latest && (
              <Section title="Intussen bewaard door een ander" level={2}>
                <Quiet>
                  Versie {latest.number} van {latest.created_by_name ?? 'een collega'}. Bewaar je
                  nu, dan komt jouw tekst als nieuwe versie daarbovenop.
                </Quiet>
                <RichText text={latest.body} headingLevel={3} />
                <nldd-button-group>
                  <Button
                    text="Neem de andere tekst over"
                    onClick={() => {
                      setBody(latest.body);
                      setBasedOn(latest.id);
                      writeSafe(vacancyId, null);
                      save.reset();
                    }}
                  />
                </nldd-button-group>
              </Section>
            )}
            <nldd-button-group>
              <Button
                text={moved ? 'Bewaar mijn tekst' : 'Bewaar'}
                appearance="primary"
                loading={save.isPending}
                onClick={() => {
                  setProblem(null);
                  if (!body.trim()) return setProblem('De tekst is leeg.');
                  // After a conflict the save starts from the version that came in between.
                  const from = moved && latest ? latest.id : basedOn;
                  setBasedOn(from);
                  save.mutate({ body: body.trim(), basedOn: from });
                }}
              />
            </nldd-button-group>
          </>
        )}
      </Page>
    </div>
  );
}
