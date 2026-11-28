import { useRef, useState } from 'react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { fetchSteering, reportKeys, type CostCoverage } from '@/features/reports/api';
import { scopeNote } from '@/features/reports/labels';
import { Figures } from '@/features/reports/ui';
import { currentReportYear } from '@/features/reports/years';
import { formatEuro } from '@/lib/format';
import { useInstance } from '@/layout/useInstance';
import { useRouterLinks } from '@/layout/useRouterLinks';
import { PATHS } from '@/paths';
import { ActionBar } from '@/ui/ActionBar';
import { OpenRow } from '@/ui/RowActions';
import { LoadError, Loading, Page, Quiet, Stack } from '@/ui/layout';
import { useNarrow } from '@/ui/layout/useNarrow';
import { PageRange, Pager } from '@/ui/Pager';
import { PAGE_PARAM, usePaging, useSearchWords } from '@/ui/paging';
import { COST_PAGE_SIZE, costsKey, fetchCostItems, type CostItem } from './api';
import { CoverageMiniBar } from './CostBars';
import { ItemSheet, type ItemTarget } from './CostSheets';
import {
  ALL_YEARS,
  SEARCH_PARAM,
  YEAR_PARAM,
  attentionPoints,
  costItemPath,
  coverageText,
  incompleteText,
  isCounted,
  parseYear,
  referenceStateText,
  yearOptions,
} from './costText';
import './costs.css';

if (import.meta.env.MODE !== 'test') void import('./register');

function invoiceCount(item: CostItem): string {
  const count =
    item.reference_state === null ? item.invoice_lines.length : item.executor_lines.length;
  if (count === 0) return 'Nog geen facturen';
  return count === 1 ? '1 factuur' : `${count} facturen`;
}

/** The share a budget covers, in words and as an amount. */
function coveredText(item: CostItem): string {
  return item.covered_cents === null
    ? coverageText(item)
    : `${coverageText(item)}, ${formatEuro(item.covered_cents)}`;
}

/** What the figures are over: all cost items or the reader's, and the year. */
function coverNote(scope: CostCoverage['scope'], year: number | null): string {
  const period = year === null ? 'over de hele looptijd' : `met de facturen van ${year}`;
  return scopeNote(
    scope,
    `Alle kostenposten, ${period}.`,
    `De kostenposten die door je eigen opdrachten worden gedekt, ${period}.`,
  );
}

/** The totals exist per year only; over the whole duration the rows say it. */
function CoverFigures({ costs }: { costs: CostCoverage }) {
  const missing = costs.incomplete_by ?? [];
  return (
    <Figures
      label="Kosten in het kort"
      {...(missing.length > 0 ? { note: incompleteText(missing) } : {})}
      figures={[
        {
          label: 'Ongedekt',
          value: formatEuro(costs.uncovered_cents),
          ...(costs.uncovered_cents > 0
            ? {
                attention: 'Geen begrotingsregel dekt dit',
                detail: `van ${formatEuro(costs.forecast_cents)} verwachte kosten`,
              }
            : { quiet: true, detail: 'alle kosten zijn gedekt' }),
        },
        {
          label: 'Verwachte kosten',
          value: formatEuro(costs.forecast_cents),
          quiet: costs.forecast_cents === 0,
        },
        {
          label: 'Gedekt door begrotingsregels',
          value: formatEuro(costs.covered_cents),
          quiet: costs.covered_cents === 0,
        },
      ]}
    />
  );
}

/**
 * External costs: how the year stands, then per cost item what it is expected
 * to be against its budget and how much of it a budget covers. What needs
 * attention comes first: money nobody pays for, an overrun, an invoice without
 * its document.
 */
export function CostsPage() {
  const instance = useInstance();
  const navigate = useNavigate();
  const rootRef = useRef<HTMLDivElement>(null);
  useRouterLinks(rootRef);
  const [searchParams, setSearchParams] = useSearchParams();
  const year = parseYear(searchParams.get(YEAR_PARAM));
  const [words, setWords, search] = useSearchWords(SEARCH_PARAM);
  // The server orders the list (what needs attention first) and sends a page.
  const asked = usePaging(undefined, COST_PAGE_SIZE).page;
  const query = useQuery({
    queryKey: costsKey(year, asked, search),
    queryFn: () => fetchCostItems(year, asked, search),
    placeholderData: keepPreviousData,
  });
  const paging = usePaging(query.data?.total, COST_PAGE_SIZE);
  const items = query.data?.items ?? [];
  const mayCreate = query.data?.may_create ?? false;
  const [adding, setAdding] = useState<ItemTarget | null>(null);
  // The column Dekking follows the width of the table, which is the window minus
  // the margins of the page: from this width on it is gone, so the row says it.
  const tableNarrow = useNarrow('(max-width: 720px)');
  const coverYear = String(year ?? currentReportYear());
  // Its own request, so a problem with it never hides the list.
  const cover = useQuery({
    queryKey: reportKeys.steering(coverYear),
    queryFn: () => fetchSteering(coverYear),
    select: (steering) => steering.costs,
  });

  const setYear = (value: string) =>
    setSearchParams(
      (current) => {
        const next = new URLSearchParams(current);
        if (value === ALL_YEARS) next.delete(YEAR_PARAM);
        else next.set(YEAR_PARAM, value);
        // Another year, another order: start at the first page.
        next.delete(PAGE_PARAM);
        return next;
      },
      { replace: true },
    );

  return (
    <div ref={rootRef}>
      <Page
        kind="list"
        title="Kosten"
        instanceName={instance?.name}
        back={{ href: PATHS.money, text: 'Terug naar Geld' }}
      >
        <ActionBar
          label="Kostenposten zoeken, filteren en acties"
          search={{ label: 'Zoek op kostenpost', value: words, onChange: setWords }}
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
            mayCreate
              ? [
                  {
                    text: 'Nieuwe kostenpost',
                    onClick: () => setAdding({ item: null }),
                    primary: true,
                  },
                ]
              : []
          }
        />
        {cover.data && (
          <Stack gap="related">
            <Quiet>{coverNote(cover.data.scope, year)}</Quiet>
            {year !== null && <CoverFigures costs={cover.data} />}
          </Stack>
        )}
        {query.isPending && <Loading />}
        {query.isError && <LoadError error={query.error} retry={() => void query.refetch()} />}
        {query.data && (
          <Stack gap="related">
            <PageRange paging={paging} noun="kostenposten" />
            <nldd-table
              accessible-label="Kostenposten"
              columns="minmax(220px,1fr) 180px 200px"
              sm-columns="minmax(150px,1fr) 130px"
            >
              <nldd-table-row slot="header">
                <nldd-text-cell text="Kostenpost" />
                <nldd-text-cell text="Dekking" hide-below="md" />
                <nldd-text-cell text="Verwacht totaal" horizontal-alignment="right" />
              </nldd-table-row>
              {items.map((item) => {
                const path = costItemPath(item.id, year);
                const points = attentionPoints(item);
                const counted = isCounted(item);
                const over = counted && item.variance_cents < 0;
                const detail = [
                  ...(item.reference_state === null
                    ? []
                    : [referenceStateText(item.reference_state, item.executor_name)]),
                  ...(counted ? [invoiceCount(item)] : []),
                  ...(tableNarrow ? [coveredText(item)] : []),
                  ...points,
                ];
                return (
                  <OpenRow key={item.id} onOpen={() => navigate(path)}>
                    <nldd-cell row-header>
                      <nldd-container gap="4">
                        <nldd-link href={path} text={item.description} />
                        <nldd-text size="sm">
                          <span>{detail.join(' · ')}</span>
                        </nldd-text>
                      </nldd-container>
                    </nldd-cell>
                    <nldd-cell hide-below="md">
                      <nldd-container gap="4">
                        {counted && <CoverageMiniBar item={item} />}
                        <nldd-text size="sm">
                          <span>{coveredText(item)}</span>
                        </nldd-text>
                      </nldd-container>
                    </nldd-cell>
                    {counted ? (
                      <nldd-text-cell
                        text={formatEuro(item.forecast_cents)}
                        supporting-text={`van ${formatEuro(item.budgeted_cents)} begroot`}
                        horizontal-alignment="right"
                        {...(over ? { color: 'critical' } : {})}
                      />
                    ) : (
                      <nldd-text-cell
                        text={formatEuro(item.budgeted_cents)}
                        {...(item.budgeted_cents === null ? {} : { 'supporting-text': 'begroot' })}
                        horizontal-alignment="right"
                      />
                    )}
                  </OpenRow>
                );
              })}
              <nldd-inline-dialog
                slot="empty"
                text={
                  search
                    ? `Geen kostenposten gevonden voor "${search}"`
                    : 'Er zijn geen kostenposten om te tonen'
                }
                supporting-text={
                  search
                    ? 'Je zoekt op de omschrijving van de kostenpost.'
                    : 'Je ziet hier kostenposten die worden gedekt door een opdracht die je beheert.'
                }
              />
            </nldd-table>
            <Pager paging={paging} label="Pagina's van de kostenposten" />
          </Stack>
        )}
      </Page>
      <ItemSheet
        target={adding}
        onClose={() => setAdding(null)}
        onCreated={(item) => navigate(costItemPath(item.id, year))}
      />
    </div>
  );
}
