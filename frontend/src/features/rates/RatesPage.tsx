import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { errorMessage } from '@/api/client';
import { formatDate, formatEuro } from '@/lib/format';
import { useInstance } from '@/layout/useInstance';
import { DateField, SelectField, SwitchField, TextField } from '@/features/team/ui/controls';
import { centsToEuroInput, eurosToCents, percentInput } from '@/features/team/ui/money';
import { ConfirmDialog } from '@/features/team/ui/overlays';
import { Section } from '@/features/team/ui/section';
import { ActionBar } from '@/ui/ActionBar';
import { EmptyNotice, ErrorNotice, FormSheet, Loading, Page, Quiet, Stack } from '@/ui/layout';
import { OpenCell, OpenRow, ROW_ACTIONS_COLUMN, RowActions, type RowAction } from '@/ui/RowActions';
import {
  CATEGORIES,
  RATE_CARDS_KEY,
  ROUNDING_LABELS,
  activateRateCard,
  activationKey,
  closeRateCard,
  coverageKey,
  createRateCard,
  fetchActivationPreview,
  fetchIndexationPreview,
  fetchRateCards,
  fetchValidRates,
  previewKey,
  setRateBand,
  setScaleBand,
  updateRateCard,
  type Indexation,
  type NewCard,
  type RateCard,
  type Rounding,
} from './api';
import { activationSentences } from './impact';
import {
  MOMENT_COLORS,
  proposedStart,
  latestEnd,
  momentLabel,
  momentOf,
  todayIso,
  validityText,
} from './validity';

/** The highest increase the server accepts, in percent. */
const MAX_INCREASE_PCT = 25;
const ROUNDINGS: Rounding[] = ['euro', 'ten', 'fifty'];

type Editing =
  | null
  | { kind: 'new' }
  | { kind: 'band'; category: string; cents: number | null }
  | { kind: 'scale'; scale: number | null; category: string }
  | { kind: 'details'; card: RateCard }
  | { kind: 'activate'; card: RateCard }
  | { kind: 'close'; card: RateCard }
  | { kind: 'unlock'; card: RateCard };

/** One row of the time line: a card, or a stretch no card prices. */
type TimelineRow = { kind: 'card'; card: RateCard } | { kind: 'gap'; start: string; end: string };

function scalesOf(card: RateCard, category: string): string {
  const scales = card.scale_bands.filter((b) => b.category === category).map((b) => b.scale);
  return scales.length ? scales.join(', ') : 'Geen';
}

/** The cards newest first, with a row for every stretch between them that no card prices. */
function timeline(
  cards: RateCard[],
  gaps: { start_date: string; end_date: string }[],
): TimelineRow[] {
  const rows: TimelineRow[] = [
    ...cards.map((card): TimelineRow => ({ kind: 'card', card })),
    ...gaps.map((gap): TimelineRow => ({ kind: 'gap', start: gap.start_date, end: gap.end_date })),
  ];
  const start = (row: TimelineRow) => (row.kind === 'card' ? row.card.valid_from : row.start);
  return rows.sort((a, b) => (start(a) < start(b) ? 1 : start(a) > start(b) ? -1 : 0));
}

/**
 * Rate cards over time: which card holds now, what came before and what is
 * coming. A card holds for a period that can start on any date; one card is
 * open at a time, with its rates per category and its scale mapping.
 */
export function RatesPage() {
  const instance = useInstance();
  const queryClient = useQueryClient();
  const today = todayIso();
  const query = useQuery({ queryKey: RATE_CARDS_KEY, queryFn: fetchRateCards });
  const cards = query.data?.items ?? [];
  const mayManage = query.data?.may_manage ?? false;

  // The span the cards cover, to ask the server where no card prices.
  const pricing = cards.filter((c) => c.status !== 'draft');
  const first = pricing.reduce<string | null>(
    (min, c) => (min === null || c.valid_from < min ? c.valid_from : min),
    null,
  );
  const last = pricing.reduce<string | null>((max, c) => {
    const end = c.valid_to ?? c.valid_from;
    return max === null || end > max ? end : max;
  }, null);
  const coverage = useQuery({
    queryKey: coverageKey(first ?? '', last ?? ''),
    queryFn: () => fetchValidRates(first as string, last as string),
    enabled: first !== null && last !== null && first < last,
  });
  const gaps = (coverage.data?.stretches ?? []).filter((s) => s.card_id === null);

  const current = cards.find((c) => momentOf(c, today) === 'now') ?? null;
  const [chosenId, setChosenId] = useState<string | null>(null);
  const card = cards.find((c) => c.id === chosenId) ?? current ?? cards[0] ?? null;

  const [editing, setEditing] = useState<Editing>(null);
  // Changing a closed card is unlocked per card, after an explicit confirmation.
  const [unlockedId, setUnlockedId] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [pageError, setPageError] = useState<string | null>(null);

  const closed = card?.status === 'closed';
  const unlocked = card !== null && unlockedId === card.id;
  const canEdit = mayManage && card !== null && (!closed || unlocked);
  const confirmClosed = Boolean(closed && unlocked);

  const save = useMutation({
    mutationFn: (run: () => Promise<unknown>) => run(),
    onSuccess: async () => {
      setEditing(null);
      setFormError(null);
      setPageError(null);
      await queryClient.invalidateQueries({ queryKey: ['rates'] });
    },
  });
  const submit = (run: () => Promise<unknown>, onDone?: () => void) =>
    save.mutate(run, {
      onSuccess: onDone,
      onError: (error) => setFormError(errorMessage(error)),
    });
  const open = (next: Editing) => {
    setFormError(null);
    setEditing(next);
  };

  const rowActions = (c: RateCard): RowAction[] => [
    ...(c.status === 'draft'
      ? [{ text: 'Stel vast', onSelect: () => open({ kind: 'activate', card: c }) }]
      : []),
    { text: 'Wijzig naam of einddatum', onSelect: () => open({ kind: 'details', card: c }) },
    ...(c.status === 'active'
      ? [{ text: 'Sluit deze tarievenkaart', onSelect: () => open({ kind: 'close', card: c }) }]
      : []),
  ];

  if (query.isPending) {
    return (
      <Page title="Tarieven" instanceName={instance?.name}>
        <Loading />
      </Page>
    );
  }
  if (query.isError) {
    return (
      <Page title="Tarieven" instanceName={instance?.name}>
        <ErrorNotice message={errorMessage(query.error)} />
      </Page>
    );
  }

  const rows = timeline(cards, gaps);
  const cardAction =
    !mayManage || !card
      ? null
      : card.status === 'draft'
        ? { text: 'Stel vast', onClick: () => open({ kind: 'activate', card }) }
        : closed && !unlocked
          ? { text: 'Wijzig gesloten kaart', onClick: () => open({ kind: 'unlock', card }) }
          : closed && unlocked
            ? { text: 'Stop met wijzigen', onClick: () => setUnlockedId(null) }
            : null;

  return (
    <Page title="Tarieven" instanceName={instance?.name} spacing="sections">
      <Stack gap="group">
        <ActionBar
          label="Tarievenkaarten"
          actions={
            mayManage
              ? [
                  {
                    text: 'Nieuwe tarievenkaart',
                    primary: true,
                    onClick: () => open({ kind: 'new' }),
                  },
                ]
              : []
          }
        />
        {pageError ? <ErrorNotice message={pageError} /> : null}
        {cards.length === 0 ? (
          <EmptyNotice
            text="Er is nog geen tarievenkaart"
            {...(mayManage
              ? {}
              : { supportingText: 'Een beheerder maakt de eerste tarievenkaart aan.' })}
          />
        ) : (
          <nldd-table
            accessible-label="Tarievenkaarten in de tijd"
            columns={`minmax(200px,2fr) minmax(220px,2fr) 170px ${ROW_ACTIONS_COLUMN}`}
            sm-columns={`minmax(110px,1fr) minmax(120px,auto) ${ROW_ACTIONS_COLUMN}`}
          >
            <nldd-table-row slot="header">
              <nldd-text-cell text="Tarievenkaart" />
              <nldd-text-cell hide-below="md" text="Geldigheid" />
              <nldd-text-cell text="Stand" />
              <nldd-cell />
            </nldd-table-row>
            {rows.map((row) => {
              if (row.kind === 'gap') {
                return (
                  <nldd-table-row key={`gap-${row.start}`}>
                    <nldd-text-cell text="Geen tarievenkaart" color="critical" />
                    <nldd-text-cell
                      hide-below="md"
                      text={validityText(row.start, row.end).replace('geldig ', '')}
                    />
                    <nldd-cell>
                      <nldd-badge color="critical" text="Gat: niet te prijzen" />
                    </nldd-cell>
                    <nldd-cell />
                  </nldd-table-row>
                );
              }
              const c = row.card;
              const moment = momentOf(c, today);
              const select = () => setChosenId(c.id);
              return (
                <OpenRow key={c.id} onOpen={select}>
                  <OpenCell text={c.name} accessibleLabel={`Toon ${c.name}`} onOpen={select} />
                  {/* The column says "Geldigheid": the cell gives the period only. */}
                  <nldd-text-cell
                    hide-below="md"
                    text={validityText(c.valid_from, c.valid_to).replace('geldig ', '')}
                  />
                  <nldd-cell>
                    <nldd-badge
                      color={MOMENT_COLORS[moment]}
                      text={momentLabel(moment, c.status)}
                    />
                  </nldd-cell>
                  <nldd-cell>
                    {mayManage ? <RowActions name={c.name} actions={rowActions(c)} /> : null}
                  </nldd-cell>
                </OpenRow>
              );
            })}
          </nldd-table>
        )}
      </Stack>

      {card ? (
        <Section
          title={card.name}
          supportingText={`Maandtarief per FTE, ${validityText(card.valid_from, card.valid_to)}`}
          action={cardAction}
        >
          {closed && unlocked ? (
            <nldd-banner
              variant="warning"
              text={`Je wijzigt de gesloten tarievenkaart '${card.name}'`}
              supporting-text="Elke wijziging komt in de auditlog te staan, met jouw naam en de oude en nieuwe waarde."
            />
          ) : null}
          <nldd-table
            accessible-label={`Maandtarieven van ${card.name}`}
            columns="minmax(100px,1fr) minmax(120px,1fr) minmax(140px,1fr)"
            sm-columns="minmax(90px,1fr) minmax(60px,auto) minmax(90px,auto)"
          >
            <nldd-table-row slot="header">
              <nldd-text-cell text="Categorie" />
              <nldd-text-cell text="Schalen" />
              <nldd-text-cell text="Maandtarief" horizontal-alignment="right" />
            </nldd-table-row>
            {CATEGORIES.map((category) => {
              const band = card.rate_bands.find((b) => b.category === category);
              const edit = canEdit
                ? () => open({ kind: 'band', category, cents: band?.monthly_rate_cents ?? null })
                : undefined;
              return (
                <OpenRow key={category} onOpen={edit}>
                  <OpenCell
                    text={`Categorie ${category}`}
                    onOpen={edit}
                    accessibleLabel={`Wijzig het maandtarief van categorie ${category}`}
                  />
                  <nldd-text-cell text={scalesOf(card, category)} />
                  <nldd-text-cell
                    text={band ? formatEuro(band.monthly_rate_cents) : 'Niet ingevuld'}
                    horizontal-alignment="right"
                  />
                </OpenRow>
              );
            })}
          </nldd-table>

          <Section
            level={3}
            title="Schaal naar categorie"
            supportingText="In welke categorie een inzetschaal declareert zolang deze kaart geldt"
            action={
              canEdit
                ? {
                    text: 'Schaal toevoegen',
                    onClick: () => open({ kind: 'scale', scale: null, category: 'A' }),
                  }
                : null
            }
          >
            {card.scale_bands.length === 0 ? (
              <EmptyNotice text="Er zijn nog geen schalen ingedeeld" />
            ) : (
              <nldd-table
                accessible-label={`Schalen van ${card.name}`}
                columns="minmax(100px,1fr) minmax(100px,1fr)"
              >
                <nldd-table-row slot="header">
                  <nldd-text-cell text="Schaal" />
                  <nldd-text-cell text="Categorie" />
                </nldd-table-row>
                {card.scale_bands.map((band) => {
                  const edit = canEdit
                    ? () => open({ kind: 'scale', scale: band.scale, category: band.category })
                    : undefined;
                  return (
                    <OpenRow key={band.scale} onOpen={edit}>
                      <OpenCell
                        text={`Schaal ${band.scale}`}
                        onOpen={edit}
                        accessibleLabel={`Wijzig de categorie van schaal ${band.scale}`}
                      />
                      <nldd-text-cell text={band.category} />
                    </OpenRow>
                  );
                })}
              </nldd-table>
            )}
          </Section>
        </Section>
      ) : null}

      <NewCardSheet
        open={editing?.kind === 'new'}
        today={today}
        hasCards={cards.length > 0}
        cards={cards}
        defaultIncreasePct={query.data?.default_increase_pct ?? '0'}
        busy={save.isPending}
        error={formError}
        onInvalid={setFormError}
        onClose={() => setEditing(null)}
        onSave={(newCard) =>
          save.mutate(() => createRateCard(newCard), {
            onSuccess: (created) => setChosenId((created as RateCard).id),
            onError: (error) => setFormError(errorMessage(error)),
          })
        }
      />
      <BandSheet
        editing={editing?.kind === 'band' ? editing : null}
        cardName={card?.name ?? ''}
        busy={save.isPending}
        error={formError}
        onInvalid={setFormError}
        onClose={() => setEditing(null)}
        onSave={(category, cents) =>
          card && submit(() => setRateBand(card.id, category, cents, confirmClosed))
        }
      />
      <ScaleSheet
        editing={editing?.kind === 'scale' ? editing : null}
        cardName={card?.name ?? ''}
        busy={save.isPending}
        error={formError}
        onInvalid={setFormError}
        onClose={() => setEditing(null)}
        onSave={(scale, category) =>
          card && submit(() => setScaleBand(card.id, scale, category, confirmClosed))
        }
      />
      <DetailsSheet
        card={editing?.kind === 'details' ? editing.card : null}
        busy={save.isPending}
        error={formError}
        onInvalid={setFormError}
        onClose={() => setEditing(null)}
        onSave={(target, changes) =>
          submit(() =>
            updateRateCard(
              target.id,
              changes,
              target.status === 'closed' && unlockedId === target.id,
            ),
          )
        }
      />
      <ActivateSheet
        card={editing?.kind === 'activate' ? editing.card : null}
        busy={save.isPending}
        error={formError}
        onClose={() => setEditing(null)}
        onActivate={(target) =>
          submit(
            () => activateRateCard(target.id),
            () => setChosenId(target.id),
          )
        }
      />
      <ConfirmDialog
        open={editing?.kind === 'close'}
        text={`De tarievenkaart '${editing?.kind === 'close' ? editing.card.name : ''}' sluiten?`}
        supportingText="De kaart blijft prijzen zoals nu. Een wijziging in haar periode vraagt daarna een aparte bevestiging van een beheerder en laat een auditregel achter."
        confirmText="Sluit deze tarievenkaart"
        onClose={() => setEditing(null)}
        onConfirm={() => {
          if (editing?.kind !== 'close') return;
          const target = editing.card;
          save.mutate(() => closeRateCard(target.id), {
            onError: (error) => setPageError(errorMessage(error)),
          });
        }}
      />
      <ConfirmDialog
        open={editing?.kind === 'unlock'}
        text={`'${editing?.kind === 'unlock' ? editing.card.name : ''}' is gesloten. Toch wijzigen?`}
        supportingText="Bedragen die met deze tarieven zijn berekend, veranderen mee. Elke wijziging wordt met jouw naam vastgelegd in de auditlog."
        confirmText="Wijzig gesloten kaart"
        onClose={() => setEditing(null)}
        onConfirm={() => {
          if (editing?.kind === 'unlock') setUnlockedId(editing.card.id);
          setEditing(null);
        }}
      />
    </Page>
  );
}

interface SheetCommon {
  busy: boolean;
  error: string | null;
  onClose: () => void;
  onInvalid: (message: string) => void;
}

/** "5.00" as "5", "2.50" as "2,5": the way someone would type it. */
function percentText(value: string): string {
  const number = Number(value);
  return Number.isNaN(number) ? '' : String(number).replace('.', ',');
}

function signedEuro(cents: number): string {
  return cents > 0 ? `+ ${formatEuro(cents)}` : formatEuro(cents);
}

interface NewCardSheetProps extends SheetCommon {
  open: boolean;
  today: string;
  hasCards: boolean;
  defaultIncreasePct: string;
  cards: RateCard[];
  onSave: (card: NewCard) => void;
}

/**
 * A new card from any date, as a copy of the card valid just before it, with
 * an increase and an explicit rounding. It starts as a draft.
 */
function NewCardSheet({ open, ...props }: NewCardSheetProps) {
  // Mounted while open, so every opening starts from the defaults.
  return open ? <NewCardForm {...props} /> : <ClosedSheet title="Nieuwe tarievenkaart" />;
}

/** The closed form sheet, kept in the document so opening animates. */
function ClosedSheet({ title }: { title: string }) {
  return (
    <FormSheet
      open={false}
      title={title}
      submitText="Bewaar"
      onSubmit={() => {}}
      onClose={() => {}}
    >
      {null}
    </FormSheet>
  );
}

function NewCardForm({
  today,
  cards,
  hasCards,
  defaultIncreasePct,
  busy,
  error,
  onClose,
  onInvalid,
  onSave,
}: Omit<NewCardSheetProps, 'open'>) {
  const [validFrom, setValidFrom] = useState(() => proposedStart(today, cards));
  // A card that starts before a later one ends the day before that one;
  // the end date follows the start date until someone sets it by hand.
  const [endTyped, setEndTyped] = useState<string | null>(null);
  const [name, setName] = useState('');
  const [copy, setCopy] = useState(hasCards);
  const [increase, setIncrease] = useState(percentText(defaultIncreasePct));
  const [rounding, setRounding] = useState<Rounding>('euro');

  const dateValid = /^\d{4}-\d{2}-\d{2}$/.test(validFrom);
  const follower = dateValid ? latestEnd(validFrom, cards) : null;
  const validTo = endTyped ?? follower ?? '';
  const pct = percentInput(increase);
  const pctValid = pct !== null && Number(pct) <= MAX_INCREASE_PCT;
  const indexation: Indexation | null =
    copy && dateValid && pctValid ? { validFrom, increasePct: pct, rounding } : null;

  // The server computes the new rates; the sheet only shows them.
  const preview = useQuery({
    queryKey: indexation ? previewKey(indexation) : ['rates', 'preview', 'none'],
    queryFn: () => fetchIndexationPreview(indexation as Indexation),
    enabled: indexation !== null,
    retry: false,
  });

  return (
    <FormSheet
      open
      size="wide"
      title="Nieuwe tarievenkaart"
      submitText="Maak concept"
      busy={busy}
      error={error}
      onClose={onClose}
      onSubmit={() => {
        if (!dateValid) {
          onInvalid('Vul de datum in vanaf wanneer de tarievenkaart geldt.');
          return;
        }
        if (copy && !pctValid) {
          onInvalid(`Vul een verhoging in van 0 tot en met ${MAX_INCREASE_PCT} procent.`);
          return;
        }
        if (validTo && validTo < validFrom) {
          onInvalid('De einddatum ligt voor de begindatum.');
          return;
        }
        onSave({
          validFrom,
          validTo: validTo || null,
          name: name.trim() || null,
          indexation: copy ? indexation : null,
        });
      }}
    >
      <DateField
        label="Geldig vanaf"
        supportingLabel="Elke datum kan, ook midden in een jaar"
        value={validFrom}
        onChange={setValidFrom}
        required
      />
      <DateField
        label="Geldig tot en met"
        supportingLabel={
          follower
            ? `Uiterlijk ${formatDate(follower)}: de dag erna gaat een volgende tarievenkaart in`
            : 'Leeg laten: de kaart geldt tot een volgende haar opvolgt'
        }
        optional
        value={validTo}
        onChange={setEndTyped}
      />
      <TextField
        label="Naam"
        supportingLabel="Leeg laten geeft een naam met de begindatum"
        optional
        value={name}
        onChange={setName}
      />
      {hasCards ? (
        <SwitchField
          label="Neem tarieven en schalen over van de kaart die daarvoor geldt"
          checked={copy}
          onChange={setCopy}
        />
      ) : null}
      {copy ? (
        <>
          <TextField
            label="Verhoging"
            supportingLabel={`Percentage waarmee elk maandtarief stijgt, van 0 tot en met ${MAX_INCREASE_PCT}`}
            value={increase}
            onChange={setIncrease}
            keyboard="decimal"
            required
          />
          <SelectField
            label="Afronding van de nieuwe tarieven"
            supportingLabel="De gekozen regel wordt met het percentage vastgelegd in de auditlog"
            value={rounding}
            onChange={(value) => setRounding(ROUNDINGS.find((r) => r === value) ?? 'euro')}
            options={ROUNDINGS.map((r) => ({ value: r, label: ROUNDING_LABELS[r] }))}
          />
          <nldd-container gap="8">
            <nldd-title
              size={5}
              text="Dit komt in het concept"
              heading-level={2}
              {...(preview.data
                ? { 'supporting-text': `Op basis van ${preview.data.copy_from_name}` }
                : {})}
            />
            {indexation === null ? (
              <Quiet>Vul een datum en een verhoging in om de nieuwe tarieven te zien.</Quiet>
            ) : preview.isPending ? (
              <Loading />
            ) : preview.isError ? (
              <ErrorNotice message={errorMessage(preview.error)} />
            ) : (
              <nldd-table
                accessible-label="Nieuwe maandtarieven"
                columns="90px repeat(3, minmax(100px,1fr))"
              >
                <nldd-table-row slot="header">
                  <nldd-text-cell text="Categorie" />
                  <nldd-text-cell text="Nu" horizontal-alignment="right" />
                  <nldd-text-cell text="Nieuw" horizontal-alignment="right" />
                  <nldd-text-cell text="Verschil" horizontal-alignment="right" />
                </nldd-table-row>
                {preview.data.rates.map((rate) => (
                  <nldd-table-row key={rate.category}>
                    <nldd-text-cell text={rate.category} />
                    <nldd-text-cell
                      text={formatEuro(rate.old_monthly_rate_cents)}
                      horizontal-alignment="right"
                    />
                    <nldd-text-cell
                      text={formatEuro(rate.new_monthly_rate_cents)}
                      horizontal-alignment="right"
                    />
                    <nldd-text-cell
                      text={signedEuro(rate.difference_cents)}
                      horizontal-alignment="right"
                    />
                  </nldd-table-row>
                ))}
              </nldd-table>
            )}
          </nldd-container>
        </>
      ) : null}
    </FormSheet>
  );
}

interface ActivateSheetProps {
  card: RateCard | null;
  busy: boolean;
  error: string | null;
  onClose: () => void;
  onActivate: (card: RateCard) => void;
}

/** The step before activating: in plain sentences what activating does. */
function ActivateSheet({ card, busy, error, onClose, onActivate }: ActivateSheetProps) {
  const preview = useQuery({
    queryKey: activationKey(card?.id ?? ''),
    queryFn: () => fetchActivationPreview((card as RateCard).id),
    enabled: card !== null,
    retry: false,
  });
  return (
    <FormSheet
      open={card !== null}
      size="wide"
      title={card ? `Stel ${card.name} vast` : 'Stel tarievenkaart vast'}
      submitText="Stel vast"
      busy={busy}
      error={error}
      onClose={onClose}
      onSubmit={() => {
        if (card && preview.data) onActivate(card);
      }}
    >
      {card === null ? null : preview.isPending ? (
        <Loading text="Bezig met narekenen wat er verandert" />
      ) : preview.isError ? (
        <ErrorNotice message={errorMessage(preview.error)} />
      ) : (
        <nldd-container gap="8">
          <nldd-title size={5} text="Dit gebeurt als je vaststelt" heading-level={2} />
          {activationSentences(preview.data).map((sentence) => (
            <nldd-text key={sentence}>{sentence}</nldd-text>
          ))}
        </nldd-container>
      )}
    </FormSheet>
  );
}

interface BandSheetProps extends SheetCommon {
  editing: { category: string; cents: number | null } | null;
  cardName: string;
  onSave: (category: string, cents: number) => void;
}

function BandSheet({ editing, ...props }: BandSheetProps) {
  return editing ? (
    <BandForm key={editing.category} editing={editing} {...props} />
  ) : (
    <ClosedSheet title="Maandtarief" />
  );
}

function BandForm({
  editing,
  cardName,
  busy,
  error,
  onClose,
  onInvalid,
  onSave,
}: Omit<BandSheetProps, 'editing'> & { editing: { category: string; cents: number | null } }) {
  const [amount, setAmount] = useState(centsToEuroInput(editing.cents));
  return (
    <FormSheet
      open
      title={`Maandtarief categorie ${editing.category}, ${cardName}`}
      submitText="Bewaar"
      busy={busy}
      error={error}
      onClose={onClose}
      onSubmit={() => {
        const cents = eurosToCents(amount);
        if (cents === null || cents < 0) {
          onInvalid('Vul een bedrag in euro in, bijvoorbeeld 18000.');
          return;
        }
        onSave(editing.category, cents);
      }}
    >
      <TextField
        label="Maandtarief per FTE"
        supportingLabel="In euro"
        value={amount}
        onChange={setAmount}
        keyboard="decimal"
        required
      />
    </FormSheet>
  );
}

interface ScaleSheetProps extends SheetCommon {
  editing: { scale: number | null; category: string } | null;
  cardName: string;
  onSave: (scale: number, category: string) => void;
}

function ScaleSheet({ editing, ...props }: ScaleSheetProps) {
  return editing ? (
    <ScaleForm key={String(editing.scale)} editing={editing} {...props} />
  ) : (
    <ClosedSheet title="Schaal" />
  );
}

function ScaleForm({
  editing,
  cardName,
  busy,
  error,
  onClose,
  onInvalid,
  onSave,
}: Omit<ScaleSheetProps, 'editing'> & { editing: { scale: number | null; category: string } }) {
  const [scale, setScale] = useState(editing.scale === null ? '' : String(editing.scale));
  const [category, setCategory] = useState(editing.category);
  return (
    <FormSheet
      open
      title={
        editing.scale === null
          ? `Schaal toevoegen, ${cardName}`
          : `Categorie van schaal ${editing.scale}, ${cardName}`
      }
      submitText="Bewaar"
      busy={busy}
      error={error}
      onClose={onClose}
      onSubmit={() => {
        const number = Number.parseInt(scale, 10);
        if (!/^\d+$/.test(scale.trim()) || number < 1 || number > 30) {
          onInvalid('Vul een schaal in van 1 tot en met 30.');
          return;
        }
        onSave(number, category);
      }}
    >
      {editing.scale === null ? (
        <TextField label="Schaal" value={scale} onChange={setScale} keyboard="numeric" required />
      ) : null}
      <SelectField
        label="Categorie"
        value={category}
        onChange={setCategory}
        options={CATEGORIES.map((c) => ({ value: c, label: c }))}
      />
    </FormSheet>
  );
}

interface DetailsSheetProps extends SheetCommon {
  card: RateCard | null;
  onSave: (card: RateCard, changes: { name: string; valid_to: string | null }) => void;
}

function DetailsSheet({ card, ...props }: DetailsSheetProps) {
  return card ? (
    <DetailsForm key={card.id} card={card} {...props} />
  ) : (
    <ClosedSheet title="Naam en einddatum" />
  );
}

function DetailsForm({
  card,
  busy,
  error,
  onClose,
  onInvalid,
  onSave,
}: Omit<DetailsSheetProps, 'card'> & { card: RateCard }) {
  const [name, setName] = useState(card.name);
  const [validTo, setValidTo] = useState(card.valid_to ?? '');
  return (
    <FormSheet
      open
      title={`Naam en einddatum van ${card.name}`}
      submitText="Bewaar"
      busy={busy}
      error={error}
      onClose={onClose}
      onSubmit={() => {
        if (!name.trim()) {
          onInvalid('Geef de tarievenkaart een naam.');
          return;
        }
        if (validTo && validTo < card.valid_from) {
          onInvalid('De einddatum ligt voor de begindatum.');
          return;
        }
        onSave(card, { name: name.trim(), valid_to: validTo || null });
      }}
    >
      <TextField label="Naam" value={name} onChange={setName} required />
      <DateField
        label="Geldig tot en met"
        supportingLabel="Leeg laten: de kaart geldt tot een volgende haar opvolgt"
        optional
        value={validTo}
        onChange={setValidTo}
      />
    </FormSheet>
  );
}
