import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { errorMessage } from '@/api/client';
import { formatEuro } from '@/lib/format';
import { useInstance } from '@/layout/useInstance';
import { PageHeading } from '@/pages/PageHeading';
import { Button, SelectField, TextField } from '@/features/team/ui/controls';
import { centsToEuroInput, eurosToCents, percentInput } from '@/features/team/ui/money';
import { ConfirmDialog, Form, Sheet } from '@/features/team/ui/overlays';
import { EmptyRows, QueryState } from '@/features/team/ui/states';
import {
  CATEGORIES,
  RATE_CARDS_KEY,
  ROUNDING_LABELS,
  STATUS_LABELS,
  createRateCard,
  fetchIndexationPreview,
  fetchRateCards,
  previewKey,
  setCardStatus,
  setRateBand,
  setScaleBand,
  type CardStatus,
  type Indexation,
  type RateCard,
  type Rounding,
} from './api';

/** The highest increase the server accepts, in percent. */
const MAX_INCREASE_PCT = 25;

type Editing =
  | { kind: 'band'; category: string; cents: number | null }
  | { kind: 'scale'; scale: number | null; category: string }
  | { kind: 'new-card' }
  | null;

const STATUS_COLORS: Record<CardStatus, 'warning' | 'success' | 'neutral'> = {
  draft: 'warning',
  active: 'success',
  closed: 'neutral',
};

function scalesOf(card: RateCard, category: string): string {
  const scales = card.scale_bands.filter((b) => b.category === category).map((b) => b.scale);
  return scales.length ? scales.join(', ') : 'Geen';
}

/** Rate cards per year: the monthly rate per category and which scale bills where. */
export function RatesPage() {
  const instance = useInstance();
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: RATE_CARDS_KEY, queryFn: fetchRateCards });
  const cards = query.data?.items ?? [];
  const mayManage = query.data?.may_manage ?? false;

  const [chosenYear, setChosenYear] = useState<number | null>(null);
  const card = cards.find((c) => c.year === chosenYear) ?? cards[0] ?? null;

  const [editing, setEditing] = useState<Editing>(null);
  // Changing a closed year is unlocked per year, after an explicit confirmation.
  const [unlockedYear, setUnlockedYear] = useState<number | null>(null);
  const [confirmUnlock, setConfirmUnlock] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [pageError, setPageError] = useState<string | null>(null);

  const closed = card?.status === 'closed';
  const unlocked = card !== null && unlockedYear === card.year;
  const canEdit = mayManage && card !== null && (!closed || unlocked);
  const confirmClosed = Boolean(closed && unlocked);

  const refresh = () => queryClient.invalidateQueries({ queryKey: ['rates'] });

  const save = useMutation({
    mutationFn: (run: () => Promise<unknown>) => run(),
    onSuccess: async () => {
      setEditing(null);
      setFormError(null);
      setPageError(null);
      await refresh();
    },
  });

  const submit = (run: () => Promise<unknown>) =>
    save.mutate(run, { onError: (error) => setFormError(errorMessage(error)) });

  const changeStatus = (status: CardStatus) => {
    if (!card) return;
    save.mutate(() => setCardStatus(card.year, status, confirmClosed), {
      onSuccess: () => {
        if (status !== 'closed') setUnlockedYear(null);
      },
      onError: (error) => setPageError(errorMessage(error)),
    });
  };

  const open = (next: Editing) => {
    setFormError(null);
    setEditing(next);
  };

  return (
    <>
      <nldd-simple-section>
        <PageHeading text="Tarieven" instanceName={instance?.name} />
        <QueryState query={query}>
          {pageError ? <nldd-banner variant="critical" text={pageError} /> : null}

          {cards.length > 0 && card ? (
            <nldd-container gap="16">
              <nldd-container layout="wrap" gap="16" vertical-alignment="bottom">
                <SelectField
                  width="240px"
                  label="Jaar"
                  value={String(card.year)}
                  onChange={(value) => setChosenYear(Number(value))}
                  options={cards.map((c) => ({
                    value: String(c.year),
                    label: `${c.year} (${STATUS_LABELS[c.status].toLowerCase()})`,
                  }))}
                />
                {mayManage ? (
                  <Button text="Nieuw jaar" onClick={() => open({ kind: 'new-card' })} />
                ) : null}
              </nldd-container>

              <nldd-title
                size={4}
                text={`Tarievenkaart ${card.year}`}
                heading-level={2}
                supporting-text="Maandtarief per FTE, per categorie"
              >
                <nldd-badge
                  slot="end"
                  color={STATUS_COLORS[card.status]}
                  text={STATUS_LABELS[card.status]}
                />
              </nldd-title>

              {closed && unlocked ? (
                <nldd-banner
                  variant="warning"
                  text={`Je wijzigt het gesloten jaar ${card.year}`}
                  supporting-text="Elke wijziging komt in de auditlog te staan, met jouw naam en de oude en nieuwe waarde."
                />
              ) : null}

              {mayManage ? (
                <nldd-button-group>
                  {card.status === 'draft' ? (
                    <Button
                      appearance="primary"
                      text="Maak actief"
                      onClick={() => changeStatus('active')}
                    />
                  ) : null}
                  {card.status === 'active' ? (
                    <Button text="Sluit dit jaar" onClick={() => changeStatus('closed')} />
                  ) : null}
                  {closed && !unlocked ? (
                    <Button text="Wijzig gesloten jaar" onClick={() => setConfirmUnlock(true)} />
                  ) : null}
                  {closed && unlocked ? (
                    <>
                      <Button text="Heropen dit jaar" onClick={() => changeStatus('active')} />
                      <Button text="Stop met wijzigen" onClick={() => setUnlockedYear(null)} />
                    </>
                  ) : null}
                </nldd-button-group>
              ) : null}

              <nldd-table
                accessible-label={`Maandtarieven ${card.year}`}
                columns={
                  canEdit
                    ? 'minmax(100px,1fr) minmax(120px,1fr) minmax(140px,1fr) 120px'
                    : 'minmax(100px,1fr) minmax(120px,1fr) minmax(140px,1fr)'
                }
              >
                <nldd-table-row slot="header">
                  <nldd-text-cell text="Categorie" />
                  <nldd-text-cell text="Schalen" />
                  <nldd-text-cell text="Maandtarief" horizontal-alignment="right" />
                  {canEdit ? <nldd-text-cell text="Actie" /> : null}
                </nldd-table-row>
                {CATEGORIES.map((category) => {
                  const band = card.rate_bands.find((b) => b.category === category);
                  return (
                    <nldd-table-row key={category}>
                      <nldd-text-cell text={category} />
                      <nldd-text-cell text={scalesOf(card, category)} />
                      <nldd-text-cell
                        text={band ? formatEuro(band.monthly_rate_cents) : 'Niet ingevuld'}
                        horizontal-alignment="right"
                      />
                      {canEdit ? (
                        <nldd-cell>
                          <Button
                            size="sm"
                            text="Wijzig"
                            accessibleLabel={`Wijzig het maandtarief van categorie ${category}`}
                            onClick={() =>
                              open({
                                kind: 'band',
                                category,
                                cents: band?.monthly_rate_cents ?? null,
                              })
                            }
                          />
                        </nldd-cell>
                      ) : null}
                    </nldd-table-row>
                  );
                })}
              </nldd-table>

              <nldd-title
                size={4}
                text="Schaal naar categorie"
                heading-level={2}
                supporting-text="In welke categorie een inzetschaal dit jaar declareert"
              />
              <nldd-table
                accessible-label={`Schalen ${card.year}`}
                columns={
                  canEdit
                    ? 'minmax(100px,1fr) minmax(100px,1fr) 120px'
                    : 'minmax(100px,1fr) minmax(100px,1fr)'
                }
              >
                <nldd-table-row slot="header">
                  <nldd-text-cell text="Schaal" />
                  <nldd-text-cell text="Categorie" />
                  {canEdit ? <nldd-text-cell text="Actie" /> : null}
                </nldd-table-row>
                {card.scale_bands.map((band) => (
                  <nldd-table-row key={band.scale}>
                    <nldd-text-cell text={String(band.scale)} />
                    <nldd-text-cell text={band.category} />
                    {canEdit ? (
                      <nldd-cell>
                        <Button
                          size="sm"
                          text="Wijzig"
                          accessibleLabel={`Wijzig de categorie van schaal ${band.scale}`}
                          onClick={() =>
                            open({ kind: 'scale', scale: band.scale, category: band.category })
                          }
                        />
                      </nldd-cell>
                    ) : null}
                  </nldd-table-row>
                ))}
                <EmptyRows text="Er zijn nog geen schalen ingedeeld" />
              </nldd-table>
              {canEdit ? (
                <nldd-button-group>
                  <Button
                    text="Schaal toevoegen"
                    onClick={() => open({ kind: 'scale', scale: null, category: 'A' })}
                  />
                </nldd-button-group>
              ) : null}
            </nldd-container>
          ) : (
            <nldd-inline-dialog
              text="Er zijn nog geen tarievenkaarten"
              supporting-text={
                mayManage
                  ? 'Begin met de tarievenkaart van een jaar.'
                  : 'Een beheerder kan de tarievenkaart van een jaar aanmaken.'
              }
            >
              {mayManage ? (
                <Button
                  slot="actions"
                  appearance="primary"
                  text="Nieuw jaar"
                  onClick={() => open({ kind: 'new-card' })}
                />
              ) : null}
            </nldd-inline-dialog>
          )}
        </QueryState>
      </nldd-simple-section>

      <BandSheet
        editing={editing?.kind === 'band' ? editing : null}
        year={card?.year ?? 0}
        submitting={save.isPending}
        error={formError}
        onClose={() => setEditing(null)}
        onSave={(category, cents) =>
          card && submit(() => setRateBand(card.year, category, cents, confirmClosed))
        }
        onInvalid={setFormError}
      />
      <ScaleSheet
        editing={editing?.kind === 'scale' ? editing : null}
        year={card?.year ?? 0}
        submitting={save.isPending}
        error={formError}
        onClose={() => setEditing(null)}
        onSave={(scale, category) =>
          card && submit(() => setScaleBand(card.year, scale, category, confirmClosed))
        }
        onInvalid={setFormError}
      />
      <NewCardSheet
        open={editing?.kind === 'new-card'}
        cards={cards}
        submitting={save.isPending}
        error={formError}
        onClose={() => setEditing(null)}
        defaultIncreasePct={query.data?.default_increase_pct ?? '0'}
        onSave={(year, indexation) =>
          save.mutate(() => createRateCard(year, indexation), {
            onSuccess: () => setChosenYear(year),
            onError: (error) => setFormError(errorMessage(error)),
          })
        }
        onInvalid={setFormError}
      />
      <ConfirmDialog
        open={confirmUnlock}
        text={`Het jaar ${card?.year ?? ''} is gesloten. Toch wijzigen?`}
        supportingText="Bedragen die met deze tarieven zijn berekend, veranderen mee. Elke wijziging wordt met jouw naam vastgelegd in de auditlog."
        confirmText="Wijzig gesloten jaar"
        onClose={() => setConfirmUnlock(false)}
        onConfirm={() => {
          setConfirmUnlock(false);
          if (card) setUnlockedYear(card.year);
        }}
      />
    </>
  );
}

interface SheetCommon {
  submitting: boolean;
  error: string | null;
  onClose: () => void;
  onInvalid: (message: string) => void;
}

interface BandSheetProps extends SheetCommon {
  editing: { category: string; cents: number | null } | null;
  year: number;
  onSave: (category: string, cents: number) => void;
}

function BandSheet({ editing, year, onSave, ...common }: BandSheetProps) {
  return (
    <Sheet
      open={editing !== null}
      title={editing ? `Maandtarief categorie ${editing.category}, ${year}` : 'Maandtarief'}
      dismissText="Annuleer"
      onClose={common.onClose}
    >
      {editing ? (
        <BandForm key={editing.category} editing={editing} onSave={onSave} {...common} />
      ) : null}
    </Sheet>
  );
}

function BandForm({
  editing,
  onSave,
  submitting,
  error,
  onInvalid,
}: Omit<BandSheetProps, 'year' | 'editing' | 'onClose'> & {
  editing: { category: string; cents: number | null };
}) {
  const [amount, setAmount] = useState(centsToEuroInput(editing.cents));
  return (
    <Form
      submitText="Bewaar"
      submitting={submitting}
      error={error}
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
    </Form>
  );
}

interface ScaleSheetProps extends SheetCommon {
  editing: { scale: number | null; category: string } | null;
  year: number;
  onSave: (scale: number, category: string) => void;
}

function ScaleSheet({ editing, year, onSave, ...common }: ScaleSheetProps) {
  const title = editing
    ? editing.scale === null
      ? `Schaal toevoegen, ${year}`
      : `Categorie van schaal ${editing.scale}, ${year}`
    : 'Schaal';
  return (
    <Sheet open={editing !== null} title={title} dismissText="Annuleer" onClose={common.onClose}>
      {editing ? (
        <ScaleForm key={String(editing.scale)} editing={editing} onSave={onSave} {...common} />
      ) : null}
    </Sheet>
  );
}

function ScaleForm({
  editing,
  onSave,
  submitting,
  error,
  onInvalid,
}: Omit<ScaleSheetProps, 'year' | 'editing' | 'onClose'> & {
  editing: { scale: number | null; category: string };
}) {
  const [scale, setScale] = useState(editing.scale === null ? '' : String(editing.scale));
  const [category, setCategory] = useState(editing.category);
  return (
    <Form
      submitText="Bewaar"
      submitting={submitting}
      error={error}
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
    </Form>
  );
}

interface NewCardSheetProps extends SheetCommon {
  open: boolean;
  cards: RateCard[];
  defaultIncreasePct: string;
  onSave: (year: number, indexation: Indexation | null) => void;
}

function NewCardSheet({ open, cards, defaultIncreasePct, onSave, ...common }: NewCardSheetProps) {
  return (
    <Sheet open={open} title="Nieuw jaar" dismissText="Annuleer" onClose={common.onClose}>
      <NewCardForm
        cards={cards}
        defaultIncreasePct={defaultIncreasePct}
        onSave={onSave}
        {...common}
      />
    </Sheet>
  );
}

const ROUNDINGS: Rounding[] = ['euro', 'ten', 'fifty'];

/** "5.00" as "5", "2.50" as "2,5": the way someone would type it. */
function percentText(value: string): string {
  const number = Number(value);
  return Number.isNaN(number) ? '' : String(number).replace('.', ',');
}

function signedEuro(cents: number): string {
  return cents > 0 ? `+ ${formatEuro(cents)}` : formatEuro(cents);
}

function NewCardForm({
  cards,
  defaultIncreasePct,
  onSave,
  submitting,
  error,
  onInvalid,
}: Omit<NewCardSheetProps, 'open' | 'onClose'>) {
  const latest = cards[0]?.year ?? null;
  const [year, setYear] = useState(latest === null ? '' : String(latest + 1));
  const [copyFrom, setCopyFrom] = useState(latest === null ? '' : String(latest));
  const [increase, setIncrease] = useState(percentText(defaultIncreasePct));
  const [rounding, setRounding] = useState<Rounding>('euro');

  const pct = percentInput(increase);
  const pctValid = pct !== null && Number(pct) <= MAX_INCREASE_PCT;
  const indexation: Indexation | null =
    copyFrom && pctValid ? { copyFrom: Number(copyFrom), increasePct: pct, rounding } : null;

  // The server computes the new rates; the sheet only shows them.
  const preview = useQuery({
    queryKey: indexation ? previewKey(indexation) : ['rates', 'preview', 'none'],
    queryFn: () => fetchIndexationPreview(indexation as Indexation),
    enabled: indexation !== null,
  });

  return (
    <Form
      submitText="Maak concept"
      submitting={submitting}
      error={error}
      onSubmit={() => {
        const number = Number.parseInt(year, 10);
        if (!/^\d{4}$/.test(year.trim()) || number < 2000 || number > 2100) {
          onInvalid('Vul een jaar in, bijvoorbeeld 2027.');
          return;
        }
        if (copyFrom && !pctValid) {
          onInvalid(`Vul een verhoging in van 0 tot en met ${MAX_INCREASE_PCT} procent.`);
          return;
        }
        onSave(number, indexation);
      }}
    >
      <TextField label="Jaar" value={year} onChange={setYear} keyboard="numeric" required />
      {cards.length > 0 ? (
        <SelectField
          label="Neem tarieven en schalen over van"
          supportingLabel="Het nieuwe jaar begint als concept; de indeling van schalen gaat ongewijzigd mee"
          value={copyFrom}
          onChange={setCopyFrom}
          emptyLabel="Niets overnemen"
          options={cards.map((c) => ({ value: String(c.year), label: String(c.year) }))}
        />
      ) : null}
      {copyFrom ? (
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
          <nldd-title
            size={5}
            text="Dit komt in het concept"
            heading-level={2}
            supporting-text="Per categorie kun je het tarief daarna nog wijzigen"
          />
          {indexation === null ? (
            <nldd-inline-dialog text="Vul een geldige verhoging in om de nieuwe tarieven te zien" />
          ) : (
            <QueryState query={preview}>
              <nldd-table
                accessible-label={`Nieuwe maandtarieven op basis van ${copyFrom}`}
                columns="70px repeat(3, minmax(100px,1fr))"
              >
                <nldd-table-row slot="header">
                  <nldd-text-cell text="Categorie" />
                  <nldd-text-cell text={`Tarief ${copyFrom}`} horizontal-alignment="right" />
                  <nldd-text-cell text="Nieuw tarief" horizontal-alignment="right" />
                  <nldd-text-cell text="Verschil" horizontal-alignment="right" />
                </nldd-table-row>
                {(preview.data?.rates ?? []).map((rate) => (
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
                <EmptyRows text={`De tarievenkaart van ${copyFrom} heeft nog geen tarieven`} />
              </nldd-table>
            </QueryState>
          )}
        </>
      ) : null}
    </Form>
  );
}
