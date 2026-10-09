import { useRef, useState } from 'react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { formatEuro } from '@/lib/format';
import { useInstance } from '@/layout/useInstance';
import { useRouterLinks } from '@/layout/useRouterLinks';
import { ActionBar } from '@/ui/ActionBar';
import { OpenRow } from '@/ui/RowActions';
import { LoadError, Loading, Page, Stack } from '@/ui/layout';
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
  parseYear,
  yearOptions,
} from './costText';
import './costs.css';

if (import.meta.env.MODE !== 'test') void import('./register');

function invoiceCount(item: CostItem): string {
  const count = item.invoice_lines.length;
  if (count === 0) return 'Nog geen facturen';
  return count === 1 ? '1 factuur' : `${count} facturen`;
}

/**
 * External costs: per cost item what it is expected to be against its
 * budget, and how much of it a budget covers. What needs attention comes
 * first: money nobody pays for, an overrun, an invoice without its document.
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
      <Page title="Kosten en facturen" instanceName={instance?.name}>
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
                const over = item.variance_cents < 0;
                return (
                  <OpenRow key={item.id} onOpen={() => navigate(path)}>
                    <nldd-cell>
                      <nldd-container gap="4">
                        <nldd-link href={path} text={item.description} />
                        <nldd-text size="sm" color="secondary">
                          {[invoiceCount(item), ...points].join(' · ')}
                        </nldd-text>
                      </nldd-container>
                    </nldd-cell>
                    <nldd-cell hide-below="md">
                      <nldd-container gap="4">
                        <CoverageMiniBar item={item} />
                        <nldd-text size="sm" color="secondary">
                          {coverageText(item)}
                        </nldd-text>
                      </nldd-container>
                    </nldd-cell>
                    <nldd-text-cell
                      text={formatEuro(item.forecast_cents)}
                      supporting-text={`van ${formatEuro(item.budgeted_cents)} begroot`}
                      horizontal-alignment="right"
                      {...(over ? { color: 'critical' } : {})}
                    />
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
