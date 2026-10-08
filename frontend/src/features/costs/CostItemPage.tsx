import { useRef, useState } from 'react';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { ApiError, errorMessage } from '@/api/client';
import { formatEuro, formatPercent } from '@/lib/format';
import { useInstance } from '@/layout/useInstance';
import { useRouterLinks } from '@/layout/useRouterLinks';
import { assignmentTabPath } from '@/features/assignments/paths';
import { Figures, type Figure } from '@/features/reports/ui';
import { Button } from '@/features/team/ui/controls';
import { ActionBar } from '@/ui/ActionBar';
import { OpenCell, OpenRow, ROW_ACTIONS_COLUMN, RowActions } from '@/ui/RowActions';
import { EmptyNotice, ErrorNotice, Loading, Page, Quiet, Section, Stack } from '@/ui/layout';
import {
  COVERAGE_OPTIONS_KEY,
  attachmentUrl,
  costItemKey,
  deleteInvoiceLine,
  fetchCostItem,
  fetchCoverageOptions,
  formatBytes,
  removeCoverage,
  type CostItem,
  type InvoiceLine,
} from './api';
import { CoverageBar, ForecastBar } from './CostBars';
import {
  CoverageSheet,
  InvoiceSheet,
  ItemSheet,
  type CoverageTarget,
  type InvoiceTarget,
  type ItemTarget,
} from './CostSheets';
import {
  ALL_YEARS,
  COST_LABELS,
  YEAR_PARAM,
  addCoverageText,
  attachmentCount,
  costsPath,
  coverageStep,
  inTimeOrder,
  lacksDocument,
  lineDetail,
  lineLabel,
  parseYear,
  varianceWord,
  whoCanEdit,
  yearOptions,
} from './costText';
import './costs.css';

if (import.meta.env.MODE !== 'test') void import('./register');

/**
 * One cost item: whether it stays within its budget and who pays for it,
 * then its invoices in the order of time, then the budget lines that cover
 * it.
 *
 * A page of its own rather than a side sheet: three parts with two tables do
 * not fit a narrow panel, and a page can be linked to. Nothing that adds or
 * changes is open by default: a row or an action opens the fields in a sheet.
 */
export function CostItemPage() {
  const { costItemId = '' } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const year = parseYear(searchParams.get(YEAR_PARAM));
  const instance = useInstance();
  const rootRef = useRef<HTMLDivElement>(null);
  useRouterLinks(rootRef);

  const query = useQuery({
    queryKey: costItemKey(costItemId, year),
    queryFn: () => fetchCostItem(costItemId, year),
    placeholderData: keepPreviousData,
    retry: false,
  });
  const item = query.data;
  const notFound = query.error instanceof ApiError && query.error.status === 404;

  const [editingItem, setEditingItem] = useState<ItemTarget | null>(null);
  const [invoice, setInvoice] = useState<InvoiceTarget | null>(null);
  const [coverage, setCoverageTarget] = useState<CoverageTarget | null>(null);

  const setYear = (value: string) =>
    setSearchParams(
      (current) => {
        const next = new URLSearchParams(current);
        if (value === ALL_YEARS) next.delete(YEAR_PARAM);
        else next.set(YEAR_PARAM, value);
        return next;
      },
      { replace: true },
    );

  return (
    <div ref={rootRef}>
      <Page
        title={item?.description ?? 'Kostenpost'}
        instanceName={instance?.name}
        spacing="sections"
      >
        <Stack gap="group">
          <nldd-link
            size="sm"
            href={costsPath(year)}
            text="Terug naar Kosten en facturen"
            start-icon="arrow-left"
          />
          {notFound ? (
            <EmptyNotice
              text="Deze kostenpost is niet gevonden"
              supportingText="De kostenpost bestaat niet, of je mag hem niet inzien."
            />
          ) : query.isError ? (
            <ErrorNotice message={errorMessage(query.error)} />
          ) : !item ? (
            <Loading />
          ) : (
            <>
              <ActionBar
                label="Jaar kiezen en acties"
                filters={[
                  {
                    label: 'Jaar',
                    value: year === null ? ALL_YEARS : String(year),
                    onChange: setYear,
                    options: yearOptions(),
                    width: '200px',
                  },
                ]}
                actions={
                  item.may_edit
                    ? [
                        { text: 'Wijzig gegevens', onClick: () => setEditingItem({ item }) },
                        {
                          text: 'Voeg factuur toe',
                          onClick: () => setInvoice({ lineId: null }),
                          primary: true,
                        },
                      ]
                    : []
                }
              />
              {!item.may_edit && <Quiet>{whoCanEdit(item)}</Quiet>}
              <State item={item} />
            </>
          )}
        </Stack>
        {item && !notFound && !query.isError && (
          <>
            <Invoices item={item} onOpen={(lineId) => setInvoice({ lineId })} />
            <Coverages item={item} onOpen={setCoverageTarget} />
          </>
        )}
      </Page>
      {item && (
        <>
          <ItemSheet target={editingItem} onClose={() => setEditingItem(null)} />
          <InvoiceSheet item={item} target={invoice} onClose={() => setInvoice(null)} />
          <CoverageSheet item={item} target={coverage} onClose={() => setCoverageTarget(null)} />
        </>
      )}
    </div>
  );
}

/** The three figures a reader comes for, then the two bars that show them. */
function State({ item }: { item: CostItem }) {
  const over = item.variance_cents < 0;
  const figures: Figure[] = [
    item.budgeted_cents === 0
      ? { label: COST_LABELS.budgeted, value: formatEuro(0), detail: 'Nog niet begroot', quiet: true }
      : { label: COST_LABELS.budgeted, value: formatEuro(item.budgeted_cents) },
    { label: COST_LABELS.forecast, value: formatEuro(item.forecast_cents) },
    {
      label: COST_LABELS.variance,
      value: formatEuro(item.variance_cents),
      ...(over ? { attention: varianceWord(item) } : { detail: varianceWord(item) }),
    },
  ];
  return (
    <div className="cost-state">
      <Figures figures={figures} label={`Stand van ${item.description}`} />
      <ForecastBar item={item} />
      <CoverageBar item={item} />
    </div>
  );
}

function useChange() {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const mutation = useMutation({
    mutationFn: (run: () => Promise<unknown>) => run(),
    onSuccess: async () => {
      setError(null);
      await queryClient.invalidateQueries({ queryKey: ['costs'] });
    },
    onError: (caught) => setError(errorMessage(caught)),
  });
  return { run: mutation.mutate, error };
}

function removalText(line: InvoiceLine): string {
  const count = line.attachments.length;
  return count === 0
    ? 'De factuur verdwijnt uit de bedragen van deze kostenpost.'
    : `De factuur verdwijnt uit de bedragen van deze kostenpost, en ${attachmentCount(count)} wordt mee verwijderd. Dat is niet terug te halen.`;
}

interface InvoicesProps {
  item: CostItem;
  onOpen: (lineId: string) => void;
}

/**
 * The invoices in the order of time. One that has come in shows its document
 * as a download; one that is still expected carries a label and steps back.
 */
function Invoices({ item, onOpen }: InvoicesProps) {
  const change = useChange();
  const lines = inTimeOrder(item.invoice_lines);
  const actions = item.may_edit ? ` ${ROW_ACTIONS_COLUMN}` : '';
  return (
    <Section title="Facturen">
      {change.error && <ErrorNotice message={change.error} />}
      <nldd-table
        accessible-label={`Facturen van ${item.description}`}
        columns={`minmax(200px,1.2fr) minmax(160px,1fr) 130px${actions}`}
        sm-columns={`minmax(140px,1fr) 110px${actions}`}
      >
        <nldd-table-row slot="header">
          <nldd-text-cell text="Factuur" />
          <nldd-text-cell text="Bijlage" hide-below="md" />
          <nldd-text-cell text="Bedrag" horizontal-alignment="right" />
          {item.may_edit && <nldd-text-cell />}
        </nldd-table-row>
        {lines.map((line) => {
          const name = lineLabel(line);
          const open = item.may_edit ? () => onOpen(line.id) : undefined;
          const expected = line.kind === 'estimate';
          return (
            <OpenRow key={line.id} {...(open ? { onOpen: open } : {})}>
              <OpenCell
                text={name}
                supportingText={lineDetail(line)}
                {...(open ? { onOpen: open, accessibleLabel: `Bewerk factuur ${name}` } : {})}
              >
                {expected && <nldd-badge size="sm" color="neutral" text="Verwacht" />}
              </OpenCell>
              {line.attachments.length > 0 ? (
                <nldd-cell hide-below="md">
                  <nldd-container gap="4">
                    {line.attachments.map((attachment) => (
                      <nldd-link
                        key={attachment.id}
                        size="sm"
                        href={attachmentUrl(item.id, line.id, attachment.id)}
                        text={attachment.filename}
                        start-icon="download"
                        accessible-label={`Download ${attachment.filename}, ${formatBytes(attachment.size_bytes)}`}
                      />
                    ))}
                  </nldd-container>
                </nldd-cell>
              ) : (
                <nldd-text-cell
                  hide-below="md"
                  size="sm"
                  color="secondary"
                  text={lacksDocument(line) ? 'Bijlage ontbreekt' : ''}
                />
              )}
              <nldd-text-cell
                text={formatEuro(line.amount_cents)}
                horizontal-alignment="right"
                {...(expected ? { color: 'secondary' } : {})}
              />
              {item.may_edit && (
                <RowActions
                  name={`factuur ${name}`}
                  actions={[
                    {
                      text: 'Verwijder factuur',
                      destructive: true,
                      confirm: {
                        text: `Factuur '${name}' verwijderen?`,
                        supportingText: removalText(line),
                        confirmText: 'Verwijder factuur',
                      },
                      onSelect: () => change.run(() => deleteInvoiceLine(item.id, line.id)),
                    },
                  ]}
                />
              )}
            </OpenRow>
          );
        })}
        <nldd-inline-dialog slot="empty" text="Nog geen facturen vastgelegd" />
      </nldd-table>
    </Section>
  );
}

interface CoveragesProps {
  item: CostItem;
  onOpen: (target: CoverageTarget) => void;
}

/**
 * Who pays, by name: the segments of the bar as rows. A row leads to the
 * finances of the assignment whose budget line covers the share.
 */
function Coverages({ item, onOpen }: CoveragesProps) {
  const navigate = useNavigate();
  const change = useChange();
  const options = useQuery({ queryKey: COVERAGE_OPTIONS_KEY, queryFn: fetchCoverageOptions });
  const covering = new Set(item.coverages.map((coverage) => coverage.budget_line_id));
  const mayAdd = (options.data?.items ?? []).some((line) => !covering.has(line.budget_line_id));
  const hidden = Number(item.hidden_coverage_pct) > 0;
  const uncovered = item.uncovered_cents !== null && item.uncovered_cents > 0;
  const anyEditable = item.coverages.some((coverage) => coverage.may_edit);
  const actions = anyEditable ? ` ${ROW_ACTIONS_COLUMN}` : '';

  return (
    <Section title="Dekking">
      {change.error && <ErrorNotice message={change.error} />}
      <nldd-table
        accessible-label={`Dekking van ${item.description}`}
        columns={`minmax(180px,1fr) 130px${actions}`}
        sm-columns={`minmax(140px,1fr) 110px${actions}`}
      >
        <nldd-table-row slot="header">
          <nldd-text-cell text="Opdracht en begrotingsregel" />
          <nldd-text-cell text="Bedrag" horizontal-alignment="right" />
          {anyEditable && <nldd-text-cell />}
        </nldd-table-row>
        {item.coverages.map((coverage, index) => {
          const finance = assignmentTabPath(coverage.assignment_id, 'finance');
          return (
            <OpenRow key={coverage.budget_line_id} onOpen={() => navigate(finance)}>
              <nldd-cell>
                <nldd-container gap="4">
                  <span className="cost-line-name cost-chart">
                    <span className="cost-swatch" data-step={coverageStep(index)} aria-hidden="true" />
                    <nldd-link href={finance} text={coverage.assignment_name} />
                  </span>
                  <nldd-text size="sm" color="secondary">
                    {coverage.budget_line_description}
                  </nldd-text>
                </nldd-container>
              </nldd-cell>
              <nldd-text-cell
                text={formatEuro(coverage.amount_cents)}
                supporting-text={formatPercent(coverage.pct)}
                horizontal-alignment="right"
              />
              {anyEditable && (
                <RowActions
                  name={`de dekking door ${coverage.assignment_name}`}
                  actions={
                    coverage.may_edit
                      ? [
                          {
                            text: 'Wijzig aandeel',
                            onSelect: () => onOpen({ coverage, pct: coverage.pct }),
                          },
                          {
                            text: 'Verwijder dekking',
                            destructive: true,
                            confirm: {
                              text: 'Deze dekking verwijderen?',
                              supportingText: `${coverage.budget_line_description} (${coverage.assignment_name}) draagt daarna niets meer van deze kostenpost.`,
                              confirmText: 'Verwijder dekking',
                            },
                            onSelect: () =>
                              change.run(() => removeCoverage(item.id, coverage.budget_line_id)),
                          },
                        ]
                      : []
                  }
                />
              )}
            </OpenRow>
          );
        })}
        {hidden && (
          <nldd-table-row>
            <nldd-cell>
              <span className="cost-line-name cost-chart">
                <span className="cost-swatch" data-kind="hidden" aria-hidden="true" />
                <nldd-text>Opdrachten die je niet kunt inzien</nldd-text>
              </span>
            </nldd-cell>
            <nldd-text-cell
              text={formatPercent(item.hidden_coverage_pct)}
              horizontal-alignment="right"
            />
            {anyEditable && <nldd-cell />}
          </nldd-table-row>
        )}
        {uncovered && (
          <nldd-table-row>
            <nldd-cell>
              <span className="cost-line-name cost-chart">
                <span className="cost-swatch" data-kind="uncovered" aria-hidden="true" />
                <nldd-text>{COST_LABELS.uncovered}</nldd-text>
              </span>
            </nldd-cell>
            <nldd-text-cell
              text={formatEuro(item.uncovered_cents)}
              supporting-text={formatPercent(item.uncovered_pct)}
              horizontal-alignment="right"
            />
            {anyEditable && <nldd-cell />}
          </nldd-table-row>
        )}
        <nldd-inline-dialog slot="empty" text="Nog geen begrotingsregel dekt deze kostenpost" />
      </nldd-table>
      {mayAdd && (uncovered || item.coverages.length === 0) && (
        <nldd-button-group>
          <Button
            text={addCoverageText(item)}
            onClick={() => onOpen({ coverage: null, pct: item.uncovered_pct ?? '' })}
          />
        </nldd-button-group>
      )}
    </Section>
  );
}
