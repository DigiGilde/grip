import { useRef, useState } from 'react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { formatEuro } from '@/lib/format';
import { useInstance } from '@/layout/useInstance';
import { useRouterLinks } from '@/layout/useRouterLinks';
import { ActionBar } from '@/ui/ActionBar';
import { OpenRow } from '@/ui/RowActions';
import { LoadError, Loading, Page } from '@/ui/layout';
import { costsKey, fetchCostItems, type CostItem } from './api';
import { CoverageMiniBar } from './CostBars';
import { ItemSheet, type ItemTarget } from './CostSheets';
import {
  ALL_YEARS,
  YEAR_PARAM,
  attentionFirst,
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
  const query = useQuery({
    queryKey: costsKey(year),
    queryFn: () => fetchCostItems(year),
    placeholderData: keepPreviousData,
  });
  const items = attentionFirst(query.data?.items ?? []);
  const mayCreate = query.data?.may_create ?? false;
  const [adding, setAdding] = useState<ItemTarget | null>(null);

  const setYear = (value: string) =>
    setSearchParams(value === ALL_YEARS ? {} : { [YEAR_PARAM]: value }, { replace: true });

  return (
    <div ref={rootRef}>
      <Page title="Kosten en facturen" instanceName={instance?.name}>
        <ActionBar
          label="Kostenposten filteren en acties"
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
              text="Er zijn geen kostenposten om te tonen"
              supporting-text="Je ziet hier kostenposten die worden gedekt door een opdracht die je beheert."
            />
          </nldd-table>
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
