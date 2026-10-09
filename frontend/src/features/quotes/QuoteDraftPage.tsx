import { QUOTE_SECTION_MARKS } from '@/ui/text/marks';
import { TextEditor } from '@/ui/TextEditor';
import { useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { ApiError, errorMessage } from '@/api/client';
import { useAuth } from '@/auth/context';
import { assignmentTabPath } from '@/features/assignments/paths';
import { Button, DateInput, TextInput } from '@/features/assignments/ui';
import { useInstance } from '@/layout/useInstance';
import { useRouterLinks } from '@/layout/useRouterLinks';
import { MoreButton } from '@/ui/Icon';
import { PATHS } from '@/paths';
import {
  ErrorNotice,
  Facts,
  FormSheet,
  LoadError,
  Loading,
  Page,
  Quiet,
  Section,
  Stack,
  StateNotice,
} from '@/ui/layout';
import { fetchQuotePreview, fetchQuotes, issueQuote, quoteKeys, type QuoteSummary } from './api';
import { formatDate, formatEuro } from '@/lib/format';
import {
  FRESH_PARAM,
  SECTION_PARAM,
  conflictOf,
  draftKeys,
  draftPreviewUrl,
  fetchDraft,
  isWritten,
  movedKeys,
  newSectionKey,
  saveLetter,
  saveOutline,
  saveSection,
  needsAttention,
  sectionState,
  type DraftSection,
  type QuoteDraft,
} from './draftApi';
import { Prose } from './Prose';
import { QuoteContentTable } from './QuoteContentTable';
import { SectionEditor } from './SectionEditor';
import { DocumentLink, MenuAction } from './ui';
import './register';
import { addDays, todayIso } from '@/lib/today';

interface SectionBlockProps {
  assignmentId: string;
  section: DraftSection;
  position: number;
  count: number;
  open: boolean;
  mayEdit: boolean;
  mayDraft: boolean;
  isAdmin: boolean;
  costs: React.ReactNode;
  /** The first section that still needs writing: the obvious next thing. */
  next: boolean;
  /** Why this section stands in the way of the quote, in the server's words. */
  problem: string | null;
  onToggle: () => void;
  onChanged: (draft: QuoteDraft) => void;
  onSaved: (draft: QuoteDraft) => void;
  onMove: (by: -1 | 1) => void;
  onRemove: () => void;
  onInclude: (included: boolean) => void;
}

/** One section of the letter: its heading and state, and opened, its text. */
function SectionBlock({
  assignmentId,
  section,
  position,
  count,
  open,
  mayEdit,
  mayDraft,
  isAdmin,
  costs,
  problem,
  onToggle,
  onChanged,
  onSaved,
  onMove,
  onRemove,
  onInclude,
}: SectionBlockProps) {
  const written = isWritten(section);
  const verb = open ? 'Sluit' : written && mayEdit ? 'Schrijf' : 'Bekijk';
  return (
    <div data-section={section.key} id={`onderdeel-${section.key}`}>
      <Stack gap="related">
        {/* One row: the heading with its state in words, and what can be done. The
            controls sit in cells of their own; a container inside a cell collapses. */}
        <nldd-list accessible-label={section.heading}>
          <nldd-list-item>
            <nldd-text-cell
              text={section.heading}
              // The state says an empty or unsettled section; another obstacle comes
              // in the server's words.
              supporting-text={
                problem && !needsAttention(section) ? problem : sectionState(section)
              }
            />
            <nldd-cell width="fit-content">
              <Button
                text={verb}
                accessibleLabel={`${verb} ${section.heading}`}
                size="sm"
                onClick={onToggle}
              />
            </nldd-cell>
            {mayEdit && (section.movable || section.optional || section.removable) ? (
              <nldd-cell width="fit-content">
                <MoreButton name={section.heading}>
                  <nldd-menu slot="popup" placement="bottom-end">
                    {section.movable && position > 0 ? (
                      <MenuAction text="Zet eerder in de brief" onSelect={() => onMove(-1)} />
                    ) : null}
                    {section.movable && position < count - 1 ? (
                      <MenuAction text="Zet later in de brief" onSelect={() => onMove(1)} />
                    ) : null}
                    {section.optional ? (
                      <MenuAction
                        text={
                          section.included ? 'Laat weg uit deze offerte' : 'Neem op in deze offerte'
                        }
                        onSelect={() => onInclude(!section.included)}
                      />
                    ) : null}
                    {section.removable ? (
                      <MenuAction text="Verwijder dit onderdeel" onSelect={onRemove} />
                    ) : null}
                  </nldd-menu>
                </MoreButton>
              </nldd-cell>
            ) : null}
          </nldd-list-item>
        </nldd-list>
        {open ? (
          section.with_costs ? (
            <Stack gap="close">
              {section.body ? <Prose text={section.body} /> : null}
              {costs}
              <DocumentLink
                href={assignmentTabPath(assignmentId, 'budget')}
                text="Wijzig de bedragen in de begroting"
              />
            </Stack>
          ) : !written || !mayEdit ? (
            <Stack gap="close">
              {section.body ? <Prose text={section.body} /> : <Quiet>Nog geen tekst.</Quiet>}
              {!written ? (
                <Quiet>
                  Dit is een standaardtekst van de organisatie en staat zo in elke offerte.
                </Quiet>
              ) : null}
              {!written && isAdmin ? (
                <DocumentLink
                  href={PATHS.quoteSender}
                  text="Wijzig de standaardteksten in Beheer"
                />
              ) : null}
            </Stack>
          ) : (
            <Stack gap="related">
              <SectionEditor
                // A model draft replaces the text: start the editor afresh on it.
                key={`${section.key}:${section.settled}:${section.origin}`}
                assignmentId={assignmentId}
                section={section}
                mayDraft={mayDraft && section.draftable}
                onChanged={onChanged}
                onSaved={onSaved}
              />
            </Stack>
          )
        ) : null}
      </Stack>
    </div>
  );
}

type Sheet = 'letter' | 'add' | 'make' | null;

/** The date a number of days from today, on the instance's calendar. */
function daysFromToday(days: number): string {
  return addDays(todayIso(), days);
}

const quoteName = (quote: QuoteSummary) =>
  quote.reference ? `offerte ${quote.reference}` : 'de vorige offerte';

/** "Offerte DG-2026-0007 van € 12.000 is gemaakt op 3 feb 2026 en getekend." */
function madeQuoteText(quote: QuoteSummary): string {
  const name = quote.reference ? `Offerte ${quote.reference}` : 'De offerte';
  const amount = quote.total_cents !== undefined ? ` van ${formatEuro(quote.total_cents)}` : '';
  const signed = quote.status === 'accepted' ? ' en getekend' : '';
  return `${name}${amount} is gemaakt op ${formatDate(quote.issued_at)}${signed}.`;
}

/**
 * Preparing a quote as the letter it is. The sections stand in the order of
 * the document; a person writes the ones that are theirs, sees the standard
 * texts and the amounts as they will print, and makes the quote when nothing
 * stands in the way.
 */
export function QuoteDraftPage() {
  const { assignmentId = '' } = useParams();
  const instance = useInstance();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { state: auth } = useAuth();
  const isAdmin = auth.status === 'authenticated' && auth.functions.includes('beheerder');
  const ref = useRef<HTMLDivElement>(null);
  useRouterLinks(ref);
  const [params, setParams] = useSearchParams();
  const openKey = params.get(SECTION_PARAM);
  const openSection = (key: string | null) => {
    const next = new URLSearchParams(params);
    if (key) next.set(SECTION_PARAM, key);
    else next.delete(SECTION_PARAM);
    setParams(next, { replace: true });
  };

  const query = useQuery({
    queryKey: draftKeys.draft(assignmentId),
    queryFn: () => fetchDraft(assignmentId),
    retry: false,
  });
  // The amounts as the quote would hold them now, and why it cannot be made.
  const preview = useQuery({
    queryKey: quoteKeys.preview(assignmentId),
    queryFn: () => fetchQuotePreview(assignmentId),
    retry: false,
  });
  // A quote that already lies there: the page then shows that one, and a
  // new draft starts only when the reader chose "Maak een nieuwe offerte".
  const made = useQuery({
    queryKey: quoteKeys.list(assignmentId),
    queryFn: () => fetchQuotes(assignmentId),
    retry: false,
  });
  const standingQuote =
    made.data?.quotes.find((quote) => quote.status === 'issued' || quote.status === 'accepted') ??
    null;
  const fresh = params.get(FRESH_PARAM) === '1';
  const showsMade = standingQuote !== null && !fresh;
  const startFresh = () => {
    const next = new URLSearchParams(params);
    next.set(FRESH_PARAM, '1');
    setParams(next, { replace: true });
  };
  const draft = query.data;
  const setDraft = (next: QuoteDraft) => {
    queryClient.setQueryData(draftKeys.draft(assignmentId), next);
  };

  const [sheet, setSheet] = useState<Sheet>(null);
  const [error, setError] = useState<string | null>(null);
  const [pageError, setPageError] = useState<string | null>(null);
  // The section that was just saved, said once under the standing sentence.
  const [savedHeading, setSavedHeading] = useState<string | null>(null);
  const change = useMutation({
    mutationFn: (action: () => Promise<QuoteDraft>) => action(),
    onSuccess: (next) => {
      setDraft(next);
      setSheet(null);
      setError(null);
      setPageError(null);
    },
  });
  /** A colleague saved first: show what stands there now and say so; nothing was changed. */
  const refused = (failure: unknown, kept: string): string => {
    const conflict = conflictOf(failure);
    if (!conflict) return errorMessage(failure);
    setDraft(conflict.current);
    return `${conflict.changedBy ?? 'Een collega'} heeft dit intussen gewijzigd. Je ziet nu de laatste stand. ${kept}`;
  };
  const inSheet = (action: () => Promise<QuoteDraft>) =>
    change.mutate(action, {
      onError: (failure) =>
        setError(
          refused(failure, 'Je invoer staat er nog; bewaar opnieuw om die te laten gelden.'),
        ),
    });
  const onPage = (action: () => Promise<QuoteDraft>) =>
    change.mutate(action, {
      onError: (failure) => setPageError(refused(failure, 'Doe je wijziging opnieuw.')),
    });

  // --- the head of the letter ---
  const [subject, setSubject] = useState('');
  const [addressee, setAddressee] = useState('');
  const [salutation, setSalutation] = useState('');
  const [opening, setOpening] = useState('');
  const [closing, setClosing] = useState('');
  const [signName, setSignName] = useState('');
  const [signFunction, setSignFunction] = useState('');
  const [signOrganisation, setSignOrganisation] = useState('');
  const editLetter = () => {
    if (!draft) return;
    setSubject(draft.subject ?? '');
    setAddressee((draft.addressee ?? []).join('\n'));
    setSalutation(draft.salutation ?? '');
    setOpening(draft.opening ?? '');
    setClosing(draft.closing ?? '');
    setSignName(draft.client_signatory?.name ?? '');
    setSignFunction(draft.client_signatory?.function ?? '');
    setSignOrganisation(draft.client_signatory?.organisation ?? '');
    setError(null);
    setSheet('letter');
  };

  // --- a section of one's own ---
  const [newHeading, setNewHeading] = useState('');

  // --- making the quote ---
  // A quote is valid for a while: thirty days is proposed, the person can
  // change the date or clear it.
  const [validUntil, setValidUntil] = useState(() => daysFromToday(30));
  const [clientReference, setClientReference] = useState('');
  const make = useMutation({
    mutationFn: () =>
      issueQuote(assignmentId, {
        valid_until: validUntil || null,
        conditions: null,
        client_reference: clientReference.trim() || null,
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['quotes'] });
      await queryClient.invalidateQueries({ queryKey: ['assignments'] });
      navigate(assignmentTabPath(assignmentId, 'quote'));
    },
    onError: (failure) => setError(errorMessage(failure)),
  });

  const sections = draft?.sections ?? [];
  const keys = sections.map((section) => section.key);
  // What is in the quote first, in the order of the letter; what was left
  // out comes after it.
  const inOrder = [
    ...sections.filter((section) => section.included),
    ...sections.filter((section) => !section.included),
  ];
  const senderProblem = draft?.sender_problem ?? null;
  const problems = [
    ...(preview.data?.problem ? [{ key: null, problem: preview.data.problem }] : []),
    ...(draft?.problems ?? []).map((item) => ({
      key: item.key as string | null,
      problem: item.problem,
    })),
  ];
  const mayEdit = draft?.may_edit === true;
  // A problem of a section is told on its row; what is left is about the budget.
  const loose = problems.filter((item) => item.key === null);
  const problemOf = (key: string) => problems.find((item) => item.key === key)?.problem ?? null;
  const waiting = sections.filter(needsAttention);
  const first = waiting[0];
  const nextKey = first?.key ?? null;
  const standing =
    problems.length === 0 && senderProblem
      ? 'De tekst is klaar. De afzender van de brief is nog niet compleet.'
      : problems.length === 0
        ? 'De offerte is klaar om te maken. Daarna wijzigt ze niet meer.'
        : !first
          ? 'De offerte kan nog niet worden gemaakt.'
          : waiting.length === 1
            ? `Nog één onderdeel te schrijven: ${first.heading}.`
            : `Nog ${waiting.length} onderdelen te schrijven. Begin met ${first.heading}.`;
  const canMake =
    mayEdit && problems.length === 0 && !senderProblem && preview.data?.can_issue === true;
  const hidden =
    query.error instanceof ApiError && (query.error.status === 404 || query.error.status === 403);
  const title = preview.data ? `Offerte voor ${preview.data.assignment_name}` : 'Offerte schrijven';

  const costs = preview.data?.content ? (
    <QuoteContentTable content={preview.data.content} label="Bedragen uit de begroting" />
  ) : (
    <Quiet>De bedragen komen uit de begroting zodra die regels heeft.</Quiet>
  );

  return (
    <div ref={ref}>
      <Page
        title={title}
        instanceName={instance?.name}
        width="960px"
        back={{ href: assignmentTabPath(assignmentId, 'quote'), text: 'Terug naar de opdracht' }}
      >
        {query.isPending ? <Loading /> : null}
        {query.isError && hidden ? (
          <StateNotice
            state="not-found"
            text="Deze offerte staat niet voor je klaar"
            detail="De opdracht bestaat niet, of je ziet de bedragen ervan niet."
          />
        ) : null}
        {query.isError && !hidden ? (
          <LoadError error={query.error} retry={() => void query.refetch()} />
        ) : null}
        {pageError ? <ErrorNotice message={pageError} /> : null}

        {draft ? (
          <>
            <Stack gap="related">
              {showsMade ? (
                <nldd-text data-made-quote>
                  {madeQuoteText(standingQuote)} Een nieuwe offerte vervangt haar.
                </nldd-text>
              ) : (
                <nldd-text>{standing}</nldd-text>
              )}
              {!showsMade && standingQuote ? (
                <nldd-text size="sm" color="secondary">
                  Deze offerte vervangt {quoteName(standingQuote)} zodra je haar maakt.
                </nldd-text>
              ) : null}
              {savedHeading ? (
                <nldd-text size="sm" color="secondary" role="status" data-saved>
                  {savedHeading} is bewaard.
                </nldd-text>
              ) : null}
              {loose.length > 0 || senderProblem ? (
                <nldd-list accessible-label="Wat nog nodig is voor de offerte" data-problems>
                  {loose.map((item) => (
                    <nldd-list-item key={item.problem}>
                      <nldd-text-cell text="Begroting" supporting-text={item.problem} />
                    </nldd-list-item>
                  ))}
                  {senderProblem ? (
                    <nldd-list-item data-sender-problem>
                      <nldd-text-cell
                        text="Afzender"
                        supporting-text={
                          draft.may_set_sender
                            ? senderProblem
                            : `${senderProblem} Vraag een beheerder om dit in te vullen.`
                        }
                      />
                      {draft.may_set_sender ? (
                        <nldd-cell width="fit-content">
                          <nldd-link href={PATHS.quoteSender} text="Vul de afzender in" size="md" />
                        </nldd-cell>
                      ) : null}
                    </nldd-list-item>
                  ) : null}
                </nldd-list>
              ) : null}
              <nldd-container layout="wrap" gap="16" vertical-alignment="center">
                {showsMade ? (
                  <>
                    <nldd-link
                      href={assignmentTabPath(assignmentId, 'quote')}
                      text="Terug naar de offerte"
                      size="md"
                    />
                    {mayEdit ? (
                      <Button text="Maak een nieuwe offerte" onClick={startFresh} />
                    ) : null}
                  </>
                ) : mayEdit ? (
                  <Button
                    text="Maak offerte"
                    appearance="primary"
                    disabled={!canMake}
                    onClick={() => {
                      setError(null);
                      setSheet('make');
                    }}
                  />
                ) : null}
                {showsMade ? null : (
                  <DocumentLink
                    href={draftPreviewUrl(assignmentId)}
                    text="Bekijk voorbeeld (pdf)"
                    newTab
                  />
                )}
              </nldd-container>
            </Stack>

            <Section title="Onderdelen" level={2}>
              <Stack gap="related">
                {inOrder.map((section) => (
                  <SectionBlock
                    key={section.key}
                    assignmentId={assignmentId}
                    section={section}
                    position={keys.indexOf(section.key)}
                    count={sections.length}
                    open={openKey === section.key}
                    // The text of a made quote is read here, not changed.
                    mayEdit={mayEdit && !showsMade}
                    mayDraft={draft.drafting_available}
                    isAdmin={isAdmin}
                    costs={costs}
                    next={section.key === nextKey}
                    problem={problemOf(section.key)}
                    onToggle={() => openSection(openKey === section.key ? null : section.key)}
                    onChanged={setDraft}
                    onSaved={(next) => {
                      // Saved: on to the next section that still needs writing,
                      // or close this one when nothing is left.
                      const following = next.sections.find(
                        (item) => item.key !== section.key && needsAttention(item),
                      );
                      openSection(following?.key ?? null);
                      setSavedHeading(section.heading);
                    }}
                    onMove={(by) =>
                      onPage(() =>
                        saveOutline(
                          assignmentId,
                          movedKeys(keys, section.key, by),
                          [],
                          draft.outline_version,
                        ),
                      )
                    }
                    onRemove={() =>
                      onPage(() =>
                        saveOutline(
                          assignmentId,
                          keys.filter((key) => key !== section.key),
                          [],
                          draft.outline_version,
                        ),
                      )
                    }
                    onInclude={(included) =>
                      onPage(() =>
                        saveSection(assignmentId, section.key, {
                          included,
                          version: section.version,
                        }),
                      )
                    }
                  />
                ))}
              </Stack>
              {mayEdit && !showsMade ? (
                <nldd-button-group>
                  <Button
                    text="Voeg een onderdeel toe"
                    size="sm"
                    onClick={() => {
                      setNewHeading('');
                      setError(null);
                      setSheet('add');
                    }}
                  />
                </nldd-button-group>
              ) : null}
            </Section>

            <Section title="Gegevens van de brief" level={2}>
              <Facts
                label="Gegevens van de brief"
                facts={[
                  { label: 'Betreft', value: draft.subject },
                  { label: 'Aan', value: (draft.addressee ?? []).join(', ') },
                  { label: 'Aanhef', value: draft.salutation },
                  {
                    label: 'Tekent namens de opdrachtgever',
                    value: [draft.client_signatory?.name, draft.client_signatory?.function]
                      .filter(Boolean)
                      .join(', '),
                  },
                ]}
              />
              {mayEdit && !showsMade ? (
                <nldd-button-group>
                  <Button text="Wijzig" size="sm" onClick={editLetter} />
                </nldd-button-group>
              ) : null}
            </Section>
          </>
        ) : null}
      </Page>

      <FormSheet
        open={sheet === 'letter'}
        title="Gegevens van de brief"
        submitText="Bewaar"
        busy={change.isPending}
        error={sheet === 'letter' ? error : null}
        onClose={() => setSheet(null)}
        onSubmit={() =>
          inSheet(() =>
            saveLetter(assignmentId, {
              head_version: draft?.head_version,
              subject: subject.trim(),
              addressee: addressee
                .split('\n')
                .map((line) => line.trim())
                .filter(Boolean),
              salutation: salutation.trim(),
              opening,
              closing,
              client_signatory: {
                ...(draft?.client_signatory ?? {}),
                name: signName.trim(),
                function: signFunction.trim(),
                organisation: signOrganisation.trim(),
              },
            }),
          )
        }
      >
        <TextInput label="Betreft" value={subject} onChange={setSubject} required />
        <TextInput
          label="Geadresseerde"
          hint="Een regel per regel van het adres"
          value={addressee}
          onChange={setAddressee}
          multiline
        />
        <TextInput label="Aanhef" value={salutation} onChange={setSalutation} />
        <TextInput label="Openingszin" value={opening} onChange={setOpening} multiline optional />
        <TextEditor
          label="Afsluiting"
          value={closing}
          onChange={setClosing}
          marks={QUOTE_SECTION_MARKS}
          rows={6}
          optional
        />
        <TextInput
          label="Wie tekent namens de opdrachtgever"
          value={signName}
          onChange={setSignName}
          optional
        />
        <TextInput label="Functie" value={signFunction} onChange={setSignFunction} optional />
        <TextInput
          label="Organisatie"
          value={signOrganisation}
          onChange={setSignOrganisation}
          optional
        />
      </FormSheet>

      <FormSheet
        open={sheet === 'add'}
        title="Onderdeel toevoegen"
        submitText="Voeg toe"
        busy={change.isPending}
        error={sheet === 'add' ? error : null}
        onClose={() => setSheet(null)}
        onSubmit={() => {
          const heading = newHeading.trim();
          if (!heading) {
            setError('Geef het onderdeel een kop.');
            return;
          }
          const key = newSectionKey(heading, keys);
          inSheet(async () => {
            const next = await saveOutline(
              assignmentId,
              [...keys, key],
              [{ key, heading }],
              draft?.outline_version,
            );
            openSection(key);
            return next;
          });
        }}
      >
        <TextInput
          label="Kop van het onderdeel"
          hint="Het komt achteraan; daarna zet je het op zijn plek."
          value={newHeading}
          onChange={setNewHeading}
          required
        />
      </FormSheet>

      <FormSheet
        open={sheet === 'make'}
        title="Offerte maken"
        submitText="Maak offerte"
        busy={make.isPending}
        error={sheet === 'make' ? error : null}
        onClose={() => setSheet(null)}
        onSubmit={() => make.mutate()}
      >
        <nldd-text>
          De offerte legt de tekst en de begroting vast zoals ze nu zijn en krijgt een eigen
          kenmerk. Daarna wijzigt ze niet meer.
        </nldd-text>
        <DateInput label="Geldig tot en met" value={validUntil} onChange={setValidUntil} optional />
        <TextInput
          label="Kenmerk van de opdrachtgever"
          hint="Bijvoorbeeld een zaak- of ordernummer. Staat op de offerte als 'Uw kenmerk'."
          value={clientReference}
          onChange={setClientReference}
          optional
        />
      </FormSheet>
    </div>
  );
}
