import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { errorMessage } from '@/api/client';
import { formatDate, formatEuro, formatMonth, formatPercent } from '@/lib/format';
import { Button, DateField, FileField, SelectField, TextField } from '@/features/team/ui/controls';
import { centsToEuroInput, eurosToCents, percentInput } from '@/features/team/ui/money';
import { ConfirmDialog, Form, Sheet } from '@/features/team/ui/overlays';
import { cancelAction } from '@/features/team/ui/actions';
import { Section } from '@/features/team/ui/section';
import { EmptyRows } from '@/features/team/ui/states';
import {
  ATTACHMENT_ACCEPT,
  ATTACHMENT_HELP,
  COVERAGE_OPTIONS_KEY,
  KIND_CHOICES,
  KIND_LABELS,
  addInvoiceLine,
  attachmentUrl,
  deleteInvoiceLine,
  fetchCoverageOptions,
  formatBytes,
  removeAttachment,
  removeCoverage,
  setCoverage,
  updateCostItem,
  updateInvoiceLine,
  uploadAttachment,
  type Attachment,
  type CostItem,
  type InvoiceLine,
  type InvoiceLineInput,
} from './api';

interface CostItemSheetProps {
  item: CostItem | null;
  onClose: () => void;
}

/** One cost item: its totals, its invoices and what covers it. */
export function CostItemSheet({ item, onClose }: CostItemSheetProps) {
  return (
    <Sheet
      open={item !== null}
      title={item?.description ?? 'Kostenpost'}
      onClose={onClose}
      width="760px"
    >
      {item ? <CostItemDetails key={item.id} item={item} /> : null}
    </Sheet>
  );
}

/**
 * What is open in the sheet. Nothing by default: every section shows what is
 * there, and an action opens the fields to add or change something. One thing
 * at a time, so the sheet never grows a second open form.
 */
type Open =
  | null
  | { kind: 'item' }
  | { kind: 'add-line' }
  | { kind: 'line'; id: string; notice?: string }
  | { kind: 'coverage' };

function useSave() {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const mutation = useMutation({
    mutationFn: (run: () => Promise<unknown>) => run(),
    onSuccess: async () => {
      setError(null);
      await queryClient.invalidateQueries({ queryKey: ['costs'] });
    },
    onError: (err) => setError(errorMessage(err)),
  });
  return { run: mutation.mutate, pending: mutation.isPending, error, setError };
}

function CostItemDetails({ item }: { item: CostItem }) {
  const [open, setOpen] = useState<Open>(null);
  const close = () => setOpen(null);
  const editedLine =
    open?.kind === 'line' ? (item.invoice_lines.find((l) => l.id === open.id) ?? null) : null;

  return (
    <nldd-container gap="32">
      <Section
        title="Bedragen"
        action={
          !item.may_edit
            ? null
            : open?.kind === 'item'
              ? cancelAction(close)
              : { text: 'Wijzig gegevens', onClick: () => setOpen({ kind: 'item' }) }
        }
      >
        {open?.kind === 'item' ? <ItemForm item={item} onDone={close} /> : <Totals item={item} />}
      </Section>

      <Section
        title="Facturen"
        supportingText="Ontvangen facturen en wat nog wordt verwacht, met de factuur zelf als bijlage"
        action={
          !item.may_edit
            ? null
            : open?.kind === 'add-line' || open?.kind === 'line'
              ? cancelAction(close)
              : {
                  text: 'Voeg factuur toe',
                  onClick: () => setOpen({ kind: 'add-line' }),
                }
        }
      >
        {open?.kind === 'add-line' ? (
          <LineForm
            item={item}
            line={null}
            onDone={close}
            onPartly={(id, notice) => setOpen({ kind: 'line', id, notice })}
          />
        ) : editedLine ? (
          <LineEditor
            key={editedLine.id}
            item={item}
            line={editedLine}
            notice={open?.kind === 'line' ? open.notice : undefined}
            onDone={close}
          />
        ) : (
          <InvoiceTable item={item} onEdit={(id) => setOpen({ kind: 'line', id })} />
        )}
      </Section>

      <Coverages
        item={item}
        open={open?.kind === 'coverage'}
        onOpen={() => setOpen({ kind: 'coverage' })}
        onClose={close}
      />
    </nldd-container>
  );
}

function Totals({ item }: { item: CostItem }) {
  const exceeded = item.covered_cents === null;
  const over = item.variance_cents < 0;
  return (
    <>
      {exceeded ? (
        <nldd-banner
          variant="critical"
          text="De dekking komt boven 100 procent uit"
          supporting-text="Pas de percentages aan; tot die tijd is het gedekte bedrag niet te bepalen."
        />
      ) : null}
      <nldd-table accessible-label={`Bedragen van ${item.description}`} columns="1fr 160px">
        <nldd-table-row slot="header">
          <nldd-text-cell text="Bedrag" />
          <nldd-text-cell text="Euro" horizontal-alignment="right" />
        </nldd-table-row>
        <nldd-table-row>
          <nldd-text-cell text="Begroot" />
          <nldd-text-cell text={formatEuro(item.budgeted_cents)} horizontal-alignment="right" />
        </nldd-table-row>
        <nldd-table-row>
          <nldd-text-cell text="Gerealiseerd" supporting-text="Ontvangen facturen" />
          <nldd-text-cell text={formatEuro(item.actual_cents)} horizontal-alignment="right" />
        </nldd-table-row>
        <nldd-table-row>
          <nldd-text-cell text="Nog gepland" supporting-text="Verwachte facturen" />
          <nldd-text-cell text={formatEuro(item.estimate_cents)} horizontal-alignment="right" />
        </nldd-table-row>
        <nldd-table-row>
          <nldd-text-cell text="Verwacht totaal" supporting-text="Gerealiseerd plus nog gepland" />
          <nldd-text-cell text={formatEuro(item.forecast_cents)} horizontal-alignment="right" />
        </nldd-table-row>
        <nldd-table-row>
          <nldd-text-cell
            text="Afwijking"
            supporting-text={over ? 'Boven begroting' : 'Begroot min verwacht totaal'}
          />
          <nldd-text-cell
            text={formatEuro(item.variance_cents)}
            horizontal-alignment="right"
            {...(over ? { color: 'critical' } : {})}
          />
        </nldd-table-row>
        <nldd-table-row>
          <nldd-text-cell
            text="Gedekt"
            supporting-text={`${formatPercent(item.pct_total)} van het verwacht totaal`}
          />
          <nldd-text-cell
            text={exceeded ? 'Onbekend' : formatEuro(item.covered_cents)}
            horizontal-alignment="right"
          />
        </nldd-table-row>
        <nldd-table-row>
          <nldd-text-cell text="Ongedekt" />
          <nldd-text-cell
            text={exceeded ? 'Onbekend' : formatEuro(item.uncovered_cents)}
            horizontal-alignment="right"
          />
        </nldd-table-row>
      </nldd-table>
    </>
  );
}

function ItemForm({ item, onDone }: { item: CostItem; onDone: () => void }) {
  const save = useSave();
  const [description, setDescription] = useState(item.description);
  const [budgeted, setBudgeted] = useState(centsToEuroInput(item.budgeted_cents));
  return (
    <Form
      submitText="Bewaar gegevens"
      submitting={save.pending}
      error={save.error}
      onSubmit={() => {
        const cents = eurosToCents(budgeted);
        if (!description.trim() || cents === null || cents < 0) {
          save.setError('Vul een omschrijving en een begroot bedrag in euro in.');
          return;
        }
        save.run(() => updateCostItem(item.id, { description, budgeted_cents: cents }), {
          onSuccess: onDone,
        });
      }}
    >
      <TextField label="Omschrijving" value={description} onChange={setDescription} required />
      <TextField
        label="Begroot bedrag"
        supportingLabel="In euro"
        value={budgeted}
        onChange={setBudgeted}
        keyboard="decimal"
        required
      />
    </Form>
  );
}

function lineLabel(line: InvoiceLine): string {
  return line.reference ?? line.description ?? KIND_LABELS[line.kind];
}

function attachmentCount(count: number): string {
  if (count === 0) return 'Geen bijlage';
  return count === 1 ? '1 bijlage' : `${count} bijlagen`;
}

interface InvoiceTableProps {
  item: CostItem;
  onEdit: (lineId: string) => void;
}

function InvoiceTable({ item, onEdit }: InvoiceTableProps) {
  return (
    <nldd-table
      accessible-label={`Facturen van ${item.description}`}
      columns={
        item.may_edit
          ? 'minmax(140px,2fr) 100px minmax(100px,1fr) 110px minmax(150px,2fr) 100px'
          : 'minmax(140px,2fr) 100px minmax(100px,1fr) 110px minmax(150px,2fr)'
      }
    >
      <nldd-table-row slot="header">
        <nldd-text-cell text="Kenmerk" />
        <nldd-text-cell text="Soort" />
        <nldd-text-cell text="Periode" />
        <nldd-text-cell text="Bedrag" horizontal-alignment="right" />
        <nldd-text-cell text="Bijlagen" />
        {item.may_edit ? <nldd-text-cell text="Actie" /> : null}
      </nldd-table-row>
      {item.invoice_lines.map((line) => (
        <nldd-table-row key={line.id}>
          <nldd-text-cell
            text={lineLabel(line)}
            {...(line.reference && line.description ? { 'supporting-text': line.description } : {})}
          />
          <nldd-text-cell text={KIND_LABELS[line.kind]} />
          <nldd-text-cell text={line.period ? formatMonth(line.period) : 'Geen periode'} />
          <nldd-text-cell text={formatEuro(line.amount_cents)} horizontal-alignment="right" />
          {line.attachments.length === 0 ? (
            <nldd-text-cell text={attachmentCount(0)} color="secondary" />
          ) : (
            <nldd-cell width="full">
              <nldd-container gap="4">
                {line.attachments.map((attachment) => (
                  <DownloadLink
                    key={attachment.id}
                    item={item}
                    line={line}
                    attachment={attachment}
                  />
                ))}
              </nldd-container>
            </nldd-cell>
          )}
          {item.may_edit ? (
            <nldd-cell>
              <Button
                size="sm"
                text="Wijzig"
                accessibleLabel={`Wijzig factuur ${lineLabel(line)}`}
                onClick={() => onEdit(line.id)}
              />
            </nldd-cell>
          ) : null}
        </nldd-table-row>
      ))}
      <EmptyRows text="Er zijn nog geen facturen vastgelegd" />
    </nldd-table>
  );
}

interface DownloadLinkProps {
  item: CostItem;
  line: InvoiceLine;
  attachment: Attachment;
}

/** A link to the file. The server always answers with a download. */
function DownloadLink({ item, line, attachment }: DownloadLinkProps) {
  return (
    <nldd-link
      size="sm"
      href={attachmentUrl(item.id, line.id, attachment.id)}
      text={attachment.filename}
      accessible-label={`Download ${attachment.filename}, ${formatBytes(attachment.size_bytes)}`}
    />
  );
}

interface LineFieldsState {
  kind: InvoiceLine['kind'];
  amount: string;
  reference: string;
  description: string;
  period: string;
}

function initialFields(line: InvoiceLine | null): LineFieldsState {
  return {
    kind: line?.kind ?? 'actual',
    amount: line ? centsToEuroInput(line.amount_cents) : '',
    reference: line?.reference ?? '',
    description: line?.description ?? '',
    period: line?.period ?? '',
  };
}

function toInput(fields: LineFieldsState): InvoiceLineInput | null {
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

interface LineFormProps {
  item: CostItem;
  line: InvoiceLine | null;
  onDone: () => void;
  /** The line was saved but a file was not: stay on the line and say so. */
  onPartly: (lineId: string, notice: string) => void;
}

/** The fields of an invoice, with the invoice itself as a file, in one step. */
function LineForm({ item, line, onDone, onPartly }: LineFormProps) {
  const save = useSave();
  const [fields, setFields] = useState(() => initialFields(line));
  const [files, setFiles] = useState<File[]>([]);
  const set = (patch: Partial<LineFieldsState>) => setFields((old) => ({ ...old, ...patch }));

  return (
    <Form
      submitText={line ? 'Bewaar factuur' : 'Leg factuur vast'}
      submitting={save.pending}
      error={save.error}
      onSubmit={() => {
        const input = toInput(fields);
        if (input === null) {
          save.setError('Vul een bedrag in euro in.');
          return;
        }
        save.run(
          async () => {
            const lineId = line
              ? (await updateInvoiceLine(item.id, line.id, input), line.id)
              : (await addInvoiceLine(item.id, input)).created_invoice_line_id;
            return { lineId, failures: await uploadAll(item.id, lineId, files) };
          },
          {
            onSuccess: (result) => {
              const { lineId, failures } = result as { lineId: string; failures: string[] };
              if (failures.length === 0) onDone();
              else
                onPartly(
                  lineId,
                  `De factuur is vastgelegd, maar niet elk bestand is toegevoegd. ${failures.join(' ')}`,
                );
            },
          },
        );
      }}
    >
      <SelectField
        label="Soort"
        value={fields.kind}
        onChange={(value) => set({ kind: value === 'estimate' ? 'estimate' : 'actual' })}
        options={[
          { value: 'actual', label: KIND_CHOICES.actual },
          { value: 'estimate', label: KIND_CHOICES.estimate },
        ]}
      />
      <TextField
        label="Bedrag"
        supportingLabel="In euro"
        value={fields.amount}
        onChange={(amount) => set({ amount })}
        keyboard="decimal"
        required
      />
      <DateField
        label="Periode"
        supportingLabel="Een dag in de maand waar het bedrag bij hoort"
        optional
        value={fields.period}
        onChange={(period) => set({ period })}
      />
      <TextField
        label="Kenmerk"
        supportingLabel="Bijvoorbeeld het factuurnummer"
        optional
        value={fields.reference}
        onChange={(reference) => set({ reference })}
      />
      <TextField
        label="Omschrijving"
        optional
        value={fields.description}
        onChange={(description) => set({ description })}
      />
      <FileField
        label={line ? 'Bijlage toevoegen' : 'De factuur zelf'}
        supportingLabel={ATTACHMENT_HELP}
        optional
        multiple
        accept={ATTACHMENT_ACCEPT}
        onChange={setFiles}
      />
    </Form>
  );
}

interface LineEditorProps {
  item: CostItem;
  line: InvoiceLine;
  notice?: string;
  onDone: () => void;
}

/** One invoice opened: its attachments, its fields, and the way to delete it. */
function LineEditor({ item, line, notice, onDone }: LineEditorProps) {
  const save = useSave();
  const [message, setMessage] = useState<string | undefined>(notice);
  const [removing, setRemoving] = useState<Attachment | null>(null);
  const [deleting, setDeleting] = useState(false);
  const count = line.attachments.length;

  return (
    <nldd-container gap="16">
      <nldd-title
        size={5}
        text={`Factuur ${lineLabel(line)}`}
        heading-level={3}
        supporting-text={`${KIND_LABELS[line.kind]}, ${formatEuro(line.amount_cents)}`}
      />
      {message ? <nldd-banner variant="warning" text={message} /> : null}
      {save.error ? <nldd-banner variant="critical" text={save.error} /> : null}

      <nldd-table
        accessible-label={`Bijlagen van factuur ${lineLabel(line)}`}
        columns="minmax(160px,2fr) 90px minmax(130px,1fr) 190px"
      >
        <nldd-table-row slot="header">
          <nldd-text-cell text="Bijlage" />
          <nldd-text-cell text="Grootte" horizontal-alignment="right" />
          <nldd-text-cell text="Toegevoegd" />
          <nldd-text-cell text="Actie" />
        </nldd-table-row>
        {line.attachments.map((attachment) => (
          <nldd-table-row key={attachment.id}>
            <nldd-cell width="full">
              <DownloadLink item={item} line={line} attachment={attachment} />
            </nldd-cell>
            <nldd-text-cell
              text={formatBytes(attachment.size_bytes)}
              horizontal-alignment="right"
            />
            <nldd-text-cell
              text={formatDate(attachment.uploaded_at)}
              {...(attachment.uploaded_by_name
                ? { 'supporting-text': `door ${attachment.uploaded_by_name}` }
                : {})}
            />
            <nldd-cell>
              <Button
                size="sm"
                text="Verwijder"
                accessibleLabel={`Verwijder bijlage ${attachment.filename}`}
                disabled={save.pending}
                onClick={() => setRemoving(attachment)}
              />
            </nldd-cell>
          </nldd-table-row>
        ))}
        <EmptyRows
          text="Deze factuur heeft nog geen bijlage"
          supportingText="Voeg hieronder de factuur zelf toe."
        />
      </nldd-table>

      <LineForm
        item={item}
        line={line}
        onDone={onDone}
        onPartly={(_id, text) => setMessage(text)}
      />

      <nldd-button-group>
        <Button
          appearance="destructive"
          text="Verwijder deze factuur"
          disabled={save.pending}
          onClick={() => setDeleting(true)}
        />
      </nldd-button-group>

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
          if (attachment) save.run(() => removeAttachment(item.id, line.id, attachment.id));
        }}
      />
      <ConfirmDialog
        open={deleting}
        destructive
        text={`Factuur '${lineLabel(line)}' verwijderen?`}
        supportingText={
          count === 0
            ? 'De factuur verdwijnt uit de bedragen van deze kostenpost.'
            : `De factuur verdwijnt uit de bedragen van deze kostenpost, en ${attachmentCount(count)} wordt mee verwijderd. Dat is niet terug te halen.`
        }
        confirmText="Verwijder factuur"
        onClose={() => setDeleting(false)}
        onConfirm={() => {
          setDeleting(false);
          save.run(() => deleteInvoiceLine(item.id, line.id), { onSuccess: onDone });
        }}
      />
    </nldd-container>
  );
}

interface CoveragesProps {
  item: CostItem;
  open: boolean;
  onOpen: () => void;
  onClose: () => void;
}

function Coverages({ item, open, onOpen, onClose }: CoveragesProps) {
  const save = useSave();
  const options = useQuery({ queryKey: COVERAGE_OPTIONS_KEY, queryFn: fetchCoverageOptions });
  const lines = options.data?.items ?? [];
  const hidden = Number(item.hidden_coverage_pct) > 0;
  const anyEditable = item.coverages.some((c) => c.may_edit);
  const [removing, setRemoving] = useState<string | null>(null);
  const removed = item.coverages.find((c) => c.budget_line_id === removing) ?? null;

  return (
    <Section
      title="Dekking"
      supportingText="Welke begrotingsregel welk deel van het verwacht totaal draagt"
      action={
        lines.length === 0
          ? null
          : open
            ? cancelAction(onClose)
            : { text: 'Leg dekking vast', onClick: onOpen }
      }
    >
      {save.error && !open ? <nldd-banner variant="critical" text={save.error} /> : null}
      {open ? (
        <CoverageForm item={item} onDone={onClose} />
      ) : (
        <>
          <nldd-table
            accessible-label={`Dekking van ${item.description}`}
            columns={
              anyEditable ? 'minmax(180px,2fr) 90px 120px 110px' : 'minmax(180px,2fr) 90px 120px'
            }
          >
            <nldd-table-row slot="header">
              <nldd-text-cell text="Begrotingsregel" />
              <nldd-text-cell text="Deel" horizontal-alignment="right" />
              <nldd-text-cell text="Bedrag" horizontal-alignment="right" />
              {anyEditable ? <nldd-text-cell text="Actie" /> : null}
            </nldd-table-row>
            {item.coverages.map((coverage) => (
              <nldd-table-row key={coverage.budget_line_id}>
                <nldd-text-cell
                  text={coverage.budget_line_description}
                  supporting-text={coverage.assignment_name}
                />
                <nldd-text-cell text={formatPercent(coverage.pct)} horizontal-alignment="right" />
                <nldd-text-cell
                  text={formatEuro(coverage.amount_cents)}
                  horizontal-alignment="right"
                />
                {anyEditable ? (
                  <nldd-cell>
                    {coverage.may_edit ? (
                      <Button
                        size="sm"
                        text="Verwijder"
                        accessibleLabel={`Verwijder de dekking door ${coverage.budget_line_description}, ${coverage.assignment_name}`}
                        disabled={save.pending}
                        onClick={() => setRemoving(coverage.budget_line_id)}
                      />
                    ) : null}
                  </nldd-cell>
                ) : null}
              </nldd-table-row>
            ))}
            <EmptyRows text="Nog geen begrotingsregel dekt deze kostenpost" />
          </nldd-table>
          {hidden ? (
            <nldd-text-cell
              size="sm"
              color="secondary"
              text={`Daarnaast dekken opdrachten die je niet kunt inzien ${formatPercent(item.hidden_coverage_pct)}.`}
            />
          ) : null}
        </>
      )}
      <ConfirmDialog
        open={removed !== null}
        destructive
        text="Deze dekking verwijderen?"
        supportingText={
          removed
            ? `${removed.budget_line_description} (${removed.assignment_name}) draagt daarna niets meer van deze kostenpost.`
            : ''
        }
        confirmText="Verwijder dekking"
        onClose={() => setRemoving(null)}
        onConfirm={() => {
          const lineId = removing;
          setRemoving(null);
          if (lineId) save.run(() => removeCoverage(item.id, lineId));
        }}
      />
    </Section>
  );
}

function CoverageForm({ item, onDone }: { item: CostItem; onDone: () => void }) {
  const save = useSave();
  const options = useQuery({ queryKey: COVERAGE_OPTIONS_KEY, queryFn: fetchCoverageOptions });
  const lines = options.data?.items ?? [];
  const [lineId, setLineId] = useState('');
  const [pct, setPct] = useState('');
  return (
    <Form
      submitText="Leg dekking vast"
      submitting={save.pending}
      error={save.error}
      onSubmit={() => {
        const value = percentInput(pct);
        if (!lineId || value === null || Number(value) <= 0 || Number(value) > 100) {
          save.setError(
            'Kies een begrotingsregel en vul een percentage boven 0 tot en met 100 in.',
          );
          return;
        }
        save.run(() => setCoverage(item.id, lineId, value), { onSuccess: onDone });
      }}
    >
      <SelectField
        label="Begrotingsregel"
        supportingLabel="Van een opdracht die je beheert; een bestaande dekking wordt vervangen"
        value={lineId}
        onChange={setLineId}
        emptyLabel="Kies een begrotingsregel"
        options={lines.map((line) => ({
          value: line.budget_line_id,
          label: line.description,
          group: line.assignment_name,
        }))}
      />
      <TextField
        label="Deel van het verwacht totaal"
        supportingLabel="Percentage"
        value={pct}
        onChange={setPct}
        keyboard="decimal"
        required
      />
    </Form>
  );
}
