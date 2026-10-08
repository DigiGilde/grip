import { useId, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { errorMessage } from '@/api/client';
import { orUndef, useNlddEvent } from '@/components/nldd/events';
import { formatDate } from '@/lib/format';
import { Button, DateField, FileField, SelectField, TextField } from '@/features/team/ui/controls';
import { centsToEuroInput, eurosToCents, percentInput } from '@/features/team/ui/money';
import { ConfirmDialog } from '@/features/team/ui/overlays';
import { FormSheet, Quiet, Stack } from '@/ui/layout';
import {
  ATTACHMENT_ACCEPT,
  ATTACHMENT_HELP,
  COVERAGE_OPTIONS_KEY,
  KIND_CHOICES,
  addInvoiceLine,
  attachmentUrl,
  createCostItem,
  fetchCoverageOptions,
  formatBytes,
  removeAttachment,
  setCoverage,
  updateCostItem,
  updateInvoiceLine,
  uploadAttachment,
  type Attachment,
  type CostItem,
  type Coverage,
  type InvoiceLine,
  type InvoiceLineInput,
} from './api';
import { addCoverageText, lineLabel, pctToInput } from './costText';

if (import.meta.env.MODE !== 'test') void import('./register');

/**
 * The fields of a sheet, started afresh every time the sheet opens. The sheet
 * itself stays in the document while closed, so it keeps what it showed last
 * while it slides out.
 */
function useSheetForm<T, F>(target: T | null, initial: (target: T) => F) {
  const [previous, setPrevious] = useState<T | null>(null);
  const [shown, setShown] = useState<T | null>(null);
  const [form, setForm] = useState<F | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  if (target !== previous) {
    setPrevious(target);
    if (target !== null) {
      setShown(target);
      setForm(initial(target));
      setError(null);
      setBusy(false);
    }
  }
  const patch = (change: Partial<F>) => setForm((old) => (old ? { ...old, ...change } : old));
  return { shown, form, patch, error, setError, busy, setBusy };
}

function useRefreshCosts() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: ['costs'] });
}

/** A new cost item, or the name and budget of an existing one. */
export type ItemTarget = { item: CostItem | null };

interface ItemSheetProps {
  target: ItemTarget | null;
  onClose: () => void;
  /** Called with the cost item after it was made. */
  onCreated?: (item: CostItem) => void;
}

export function ItemSheet({ target, onClose, onCreated }: ItemSheetProps) {
  const refresh = useRefreshCosts();
  const sheet = useSheetForm(target, ({ item }) => ({
    description: item?.description ?? '',
    budgeted: item ? centsToEuroInput(item.budgeted_cents) : '',
  }));
  const item = sheet.shown?.item ?? null;
  const form = sheet.form ?? { description: '', budgeted: '' };

  async function submit() {
    // The budget of a new cost item may follow later; an empty field is zero.
    const cents = !item && form.budgeted.trim() === '' ? 0 : eurosToCents(form.budgeted);
    if (!form.description.trim() || cents === null || cents < 0) {
      sheet.setError(
        item
          ? 'Vul een omschrijving en een begroot bedrag in euro in.'
          : 'Vul een omschrijving in, en een begroot bedrag in euro als dat bekend is.',
      );
      return;
    }
    sheet.setBusy(true);
    try {
      const body = { description: form.description.trim(), budgeted_cents: cents };
      const saved = item ? await updateCostItem(item.id, body) : await createCostItem(body);
      await refresh();
      onClose();
      if (!item) onCreated?.(saved);
    } catch (caught) {
      sheet.setError(errorMessage(caught));
    } finally {
      sheet.setBusy(false);
    }
  }

  return (
    <FormSheet
      open={target !== null}
      title={item ? 'Wijzig gegevens' : 'Nieuwe kostenpost'}
      submitText={item ? 'Bewaar gegevens' : 'Maak kostenpost'}
      onSubmit={() => void submit()}
      onClose={onClose}
      busy={sheet.busy}
      error={sheet.error}
    >
      <TextField
        label="Omschrijving"
        {...(item ? {} : { supportingLabel: 'Bijvoorbeeld een hostingcontract' })}
        value={form.description}
        onChange={(description) => sheet.patch({ description })}
        required
      />
      <TextField
        label="Begroot bedrag"
        supportingLabel="In euro"
        optional={!item}
        value={form.budgeted}
        onChange={(budgeted) => sheet.patch({ budgeted })}
        keyboard="decimal"
        required={Boolean(item)}
      />
    </FormSheet>
  );
}

/** A new invoice (`lineId` null) or an existing one. */
export type InvoiceTarget = { lineId: string | null };

interface InvoiceFields {
  kind: InvoiceLine['kind'];
  amount: string;
  reference: string;
  description: string;
  period: string;
  files: File[];
}

function invoiceInput(fields: InvoiceFields): InvoiceLineInput | null {
  const cents = eurosToCents(fields.amount);
  if (cents === null) return null;
  return {
    kind: fields.kind,
    amount_cents: cents,
    reference: fields.reference.trim() || null,
    description: fields.description.trim() || null,
    period: fields.period || null,
  };
}

/** Uploads the files one by one; returns a sentence per file that failed. */
async function uploadAll(itemId: string, lineId: string, files: File[]): Promise<string[]> {
  const failures: string[] = [];
  for (const file of files) {
    try {
      await uploadAttachment(itemId, lineId, file);
    } catch (error) {
      failures.push(`${file.name}: ${errorMessage(error)}`);
    }
  }
  return failures;
}

interface InvoiceSheetProps {
  item: CostItem;
  target: InvoiceTarget | null;
  onClose: () => void;
}

/** One invoice: its fields and the invoice itself as a file, in one step. */
export function InvoiceSheet({ item, target, onClose }: InvoiceSheetProps) {
  const refresh = useRefreshCosts();
  const find = (lineId: string | null) =>
    item.invoice_lines.find((line) => line.id === lineId) ?? null;
  const sheet = useSheetForm(target, ({ lineId }): InvoiceFields => {
    const line = find(lineId);
    return {
      kind: line?.kind ?? 'actual',
      amount: line ? centsToEuroInput(line.amount_cents) : '',
      reference: line?.reference ?? '',
      description: line?.description ?? '',
      period: line?.period ?? '',
      files: [],
    };
  });
  // A new invoice that was saved while one of its files was not: the sheet
  // goes on with that invoice, so a second try does not make it twice.
  const [created, setCreated] = useState<{ for: InvoiceTarget; lineId: string } | null>(null);
  const createdId = created && created.for === sheet.shown ? created.lineId : null;
  // The line as it is now, so an attachment that was added or removed shows.
  const line = find(createdId ?? sheet.shown?.lineId ?? null);
  const form = sheet.form;
  const [removing, setRemoving] = useState<Attachment | null>(null);

  async function submit() {
    if (!form) return;
    const input = invoiceInput(form);
    if (input === null) {
      sheet.setError('Vul een bedrag in euro in.');
      return;
    }
    sheet.setBusy(true);
    try {
      const lineId = line
        ? (await updateInvoiceLine(item.id, line.id, input), line.id)
        : (await addInvoiceLine(item.id, input)).created_invoice_line_id;
      const failures = await uploadAll(item.id, lineId, form.files);
      await refresh();
      if (failures.length === 0) {
        onClose();
      } else {
        if (!line && sheet.shown) setCreated({ for: sheet.shown, lineId });
        sheet.patch({ files: [] });
        sheet.setError(
          `De factuur is vastgelegd, maar niet elk bestand is toegevoegd. ${failures.join(' ')}`,
        );
      }
    } catch (caught) {
      sheet.setError(errorMessage(caught));
    } finally {
      sheet.setBusy(false);
    }
  }

  async function remove(attachment: Attachment) {
    if (!line) return;
    try {
      await removeAttachment(item.id, line.id, attachment.id);
      await refresh();
    } catch (caught) {
      sheet.setError(errorMessage(caught));
    }
  }

  return (
    <>
      <FormSheet
        open={target !== null}
        title={line ? `Factuur ${lineLabel(line)}` : 'Nieuwe factuur'}
        submitText={line ? 'Bewaar factuur' : 'Leg factuur vast'}
        onSubmit={() => void submit()}
        onClose={onClose}
        busy={sheet.busy}
        error={sheet.error}
      >
        <SelectField
          label="Soort"
          value={form?.kind ?? 'actual'}
          onChange={(value) => sheet.patch({ kind: value === 'estimate' ? 'estimate' : 'actual' })}
          options={[
            { value: 'actual', label: KIND_CHOICES.actual },
            { value: 'estimate', label: KIND_CHOICES.estimate },
          ]}
        />
        <TextField
          label="Bedrag"
          supportingLabel="In euro"
          value={form?.amount ?? ''}
          onChange={(amount) => sheet.patch({ amount })}
          keyboard="decimal"
          required
        />
        <DateField
          label="Periode"
          supportingLabel="Een dag in de maand waar het bedrag bij hoort"
          optional
          value={form?.period ?? ''}
          onChange={(period) => sheet.patch({ period })}
        />
        <TextField
          label="Kenmerk"
          supportingLabel="Bijvoorbeeld het factuurnummer"
          optional
          value={form?.reference ?? ''}
          onChange={(reference) => sheet.patch({ reference })}
        />
        <TextField
          label="Omschrijving"
          optional
          value={form?.description ?? ''}
          onChange={(description) => sheet.patch({ description })}
        />
        {line && line.attachments.length > 0 ? (
          <nldd-list accessible-label={`Bijlagen van factuur ${lineLabel(line)}`}>
            {line.attachments.map((attachment) => (
              <nldd-list-item key={attachment.id}>
                <nldd-cell width="full">
                  <Stack gap="tight">
                    <nldd-link
                      href={attachmentUrl(item.id, line.id, attachment.id)}
                      text={attachment.filename}
                      start-icon="download"
                      accessible-label={`Download ${attachment.filename}, ${formatBytes(attachment.size_bytes)}`}
                    />
                    <Quiet>
                      {[
                        formatBytes(attachment.size_bytes),
                        formatDate(attachment.uploaded_at),
                        attachment.uploaded_by_name ? `door ${attachment.uploaded_by_name}` : null,
                      ]
                        .filter(Boolean)
                        .join(' · ')}
                    </Quiet>
                  </Stack>
                </nldd-cell>
                <nldd-cell>
                  <Button
                    size="sm"
                    appearance="neutral-transparent"
                    text="Verwijder"
                    accessibleLabel={`Verwijder bijlage ${attachment.filename}`}
                    disabled={sheet.busy}
                    onClick={() => setRemoving(attachment)}
                  />
                </nldd-cell>
              </nldd-list-item>
            ))}
          </nldd-list>
        ) : null}
        {/* Keyed on the opening, so the picker is empty for the next invoice. */}
        <FileField
          key={sheet.shown ? (sheet.shown.lineId ?? 'new') : 'closed'}
          label={line && line.attachments.length > 0 ? 'Nog een bijlage' : 'De factuur zelf'}
          supportingLabel={ATTACHMENT_HELP}
          optional
          multiple
          accept={ATTACHMENT_ACCEPT}
          onChange={(files) => sheet.patch({ files })}
        />
      </FormSheet>
      <ConfirmDialog
        open={removing !== null}
        destructive
        text={`Bijlage '${removing?.filename ?? ''}' verwijderen?`}
        supportingText="Het bestand zelf wordt verwijderd en is daarna niet terug te halen. In de auditlog blijft staan dat het er was."
        confirmText="Verwijder bijlage"
        onClose={() => setRemoving(null)}
        onConfirm={() => {
          const attachment = removing;
          setRemoving(null);
          if (attachment) void remove(attachment);
        }}
      />
    </>
  );
}

/**
 * A share on a budget line. Without `coverage` a new one, starting from the
 * share nobody covers yet; with it the share of that line.
 */
export type CoverageTarget = { coverage: Coverage | null; pct: string };

interface PercentFieldProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  /** What is wrong with the value, said at the field. */
  problem: string | null;
}

/**
 * The share as a percentage. A refusal, by this form or by the server, is a
 * requirement the value does not meet, so it stands under the field itself.
 */
function PercentField({ label, value, onChange, problem }: PercentFieldProps) {
  const ref = useRef<HTMLElement>(null);
  const problemId = useId();
  useNlddEvent(ref, 'input', (event) => {
    const detail = (event as CustomEvent<{ value?: unknown }>).detail;
    const next = detail?.value ?? (event.target as { value?: unknown } | null)?.value;
    onChange(next === undefined || next === null ? '' : String(next));
  });
  return (
    <nldd-form-field label={label} supporting-label="Percentage van het verwacht totaal">
      <nldd-text-field
        ref={ref}
        value={value}
        keyboard="decimal"
        required
        invalid={orUndef(problem !== null)}
        {...(problem !== null ? { unmet: problemId } : {})}
      />
      <nldd-validation-list>
        <nldd-validation-item id={problemId}>{problem ?? ''}</nldd-validation-item>
      </nldd-validation-list>
    </nldd-form-field>
  );
}

interface CoverageSheetProps {
  item: CostItem;
  target: CoverageTarget | null;
  onClose: () => void;
}

export function CoverageSheet({ item, target, onClose }: CoverageSheetProps) {
  const refresh = useRefreshCosts();
  const options = useQuery({ queryKey: COVERAGE_OPTIONS_KEY, queryFn: fetchCoverageOptions });
  const covering = new Set(item.coverages.map((coverage) => coverage.budget_line_id));
  const lines = (options.data?.items ?? []).filter((line) => !covering.has(line.budget_line_id));
  const sheet = useSheetForm(target, ({ coverage, pct }) => ({
    lineId: coverage?.budget_line_id ?? '',
    pct: pctToInput(pct),
  }));
  const [problem, setProblem] = useState<string | null>(null);
  const [problemFor, setProblemFor] = useState<CoverageTarget | null>(null);
  if (sheet.shown !== problemFor) {
    setProblemFor(sheet.shown);
    setProblem(null);
  }
  const coverage = sheet.shown?.coverage ?? null;
  const form = sheet.form ?? { lineId: '', pct: '' };

  async function submit() {
    if (!form.lineId) {
      sheet.setError('Kies een begrotingsregel.');
      return;
    }
    sheet.setError(null);
    const value = percentInput(form.pct);
    if (value === null || Number(value) <= 0 || Number(value) > 100) {
      setProblem('Vul een percentage boven 0 tot en met 100 in.');
      return;
    }
    sheet.setBusy(true);
    try {
      await setCoverage(item.id, form.lineId, value);
      await refresh();
      onClose();
    } catch (caught) {
      // The server refuses a total above 100 percent; its sentence says by how much.
      setProblem(errorMessage(caught));
    } finally {
      sheet.setBusy(false);
    }
  }

  return (
    <FormSheet
      open={target !== null}
      title={coverage ? 'Wijzig aandeel' : addCoverageText(item)}
      submitText={coverage ? 'Bewaar aandeel' : 'Leg dekking vast'}
      onSubmit={() => void submit()}
      onClose={onClose}
      busy={sheet.busy}
      error={sheet.error}
    >
      {coverage ? (
        <Stack gap="tight">
          <nldd-text>{coverage.assignment_name}</nldd-text>
          <Quiet>{coverage.budget_line_description}</Quiet>
        </Stack>
      ) : (
        <SelectField
          label="Begrotingsregel"
          value={form.lineId}
          onChange={(lineId) => sheet.patch({ lineId })}
          emptyLabel="Kies een begrotingsregel"
          options={lines.map((line) => ({
            value: line.budget_line_id,
            label: line.description,
            group: line.assignment_name,
          }))}
        />
      )}
      <PercentField
        label="Aandeel"
        value={form.pct}
        onChange={(pct) => {
          sheet.patch({ pct });
          setProblem(null);
        }}
        problem={problem}
      />
    </FormSheet>
  );
}
