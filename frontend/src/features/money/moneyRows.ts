/** What the rows of Geld say, worked out from what the server sent this reader. */
import { varianceWord } from '@/features/assignments/financeText';
import { costsPath } from '@/features/costs/costText';
import type { CostItemList } from '@/features/costs/api';
import { hasFigures, type Overview, type OverviewRow } from '@/features/overview/api';
import type { Investment, Scope, Steering } from '@/features/reports/api';
import { formatEuro } from '@/lib/format';
import { PATHS } from '@/paths';
import type { LinkRow } from '@/ui/LinkRows';

export interface MoneySources {
  year: string;
  steering?: Steering;
  investment?: Investment;
  overview?: Overview;
  costs?: Pick<CostItemList, 'may_create'>;
}

const OWN = 'jouw opdrachten';

const count = (number: number, one: string, many: string) =>
  `${number} ${number === 1 ? one : many}`;

const ofScope = (scope: Scope | undefined, text: string) =>
  scope === 'own' ? `${text}, ${OWN}` : text;

/**
 * The rows of the worksheet Lopende opdrachten: running work in the chosen
 * year. A row without amounts is left out unless they could not be computed:
 * the reader may then not see them, and this is a sheet of amounts.
 */
export function runningRows(overview: Overview | undefined): OverviewRow[] {
  return (overview?.rows ?? []).filter(
    (row) =>
      row.phase === 'active' &&
      row.in_year !== false &&
      (hasFigures(row.figures) || Boolean(row.pricing_error)),
  );
}

function assignmentsRow({ year, steering, overview }: MoneySources): LinkRow | null {
  const figures = overview?.figures_active;
  if (!hasFigures(figures)) return null;
  const rows = runningRows(overview).length;
  const own = steering?.turnover?.scope === 'own';
  const amount =
    figures.variance_cents === 0 ? '' : `${formatEuro(Math.abs(figures.variance_cents))} `;
  const stand = `${amount}${varianceWord(figures).toLowerCase()} in ${year}`;
  return {
    key: 'assignments',
    text: 'Lopende opdrachten',
    href: PATHS.moneyAssignments,
    notice:
      rows === 0
        ? ofScope(steering?.turnover?.scope, `Er loopt niets in ${year}`)
        : `${rows} ${own ? 'van jouw opdrachten' : rows === 1 ? 'opdracht' : 'opdrachten'}, ${stand}`,
  };
}

function turnoverRow({ year, steering }: MoneySources): LinkRow | null {
  const turnover = steering?.turnover;
  if (!turnover) return null;
  return {
    key: 'turnover',
    text: 'Omzet',
    href: PATHS.moneyTurnover,
    notice: ofScope(
      turnover.scope,
      `${formatEuro(turnover.figures.expected_total_cents)} verwacht in ${year}`,
    ),
  };
}

/** The reading in time is at Mensen: without the money this row has nothing to say. */
function investmentRow({ year, investment }: MoneySources): LinkRow | null {
  if (!investment) return null;
  const { money, money_withheld: withheld } = investment;
  const base = { key: 'investment', text: 'Investeerruimte', href: PATHS.moneyInvestment };
  if (withheld) {
    return { ...base, notice: `Niet te tonen voor ${year}: te weinig mensen hebben een target` };
  }
  if (!money) return null;
  return {
    ...base,
    notice: money.shortfall
      ? `${formatEuro(Math.abs(money.room_cents))} tekort in ${year}`
      : `${formatEuro(money.room_cents)} ruimte in ${year}`,
  };
}

function potentialRow({ year, steering }: MoneySources): LinkRow | null {
  const pipeline = steering?.pipeline;
  if (!pipeline) return null;
  const issued = (pipeline.statuses ?? []).find((status) => status.status === 'issued');
  const waiting = issued?.count ?? 0;
  return {
    key: 'potential',
    text: 'Potentieel',
    href: PATHS.moneyPotential,
    notice: ofScope(
      pipeline.scope,
      waiting === 0
        ? `Geen offerte uit ${year} wacht op akkoord`
        : `${formatEuro(issued?.total_cents)}, ${count(waiting, 'offerte', 'offertes')} uit ${year} ${
            waiting === 1 ? 'wacht' : 'wachten'
          } op akkoord`,
    ),
  };
}

/** Without a cost item to report on, the row stays for who may add the first one. */
function costsRow({ year, steering, costs: list }: MoneySources): LinkRow | null {
  const costs = steering?.costs;
  const base = { key: 'costs', text: 'Kosten', href: costsPath(Number(year)) };
  if (!costs) return list?.may_create ? base : null;
  const missing = costs.without_document_count;
  const stand =
    costs.uncovered_cents > 0
      ? `${formatEuro(costs.uncovered_cents)} ongedekt in ${year}`
      : `Alles gedekt in ${year}`;
  return {
    ...base,
    notice: ofScope(
      costs.scope,
      missing > 0 ? `${stand}, ${count(missing, 'factuur', 'facturen')} zonder bijlage` : stand,
    ),
  };
}

/** Billing is about now: what is open, whatever year it was earned in. */
function billingRow({ steering, overview }: MoneySources): LinkRow | null {
  const toDeliver = overview?.to_deliver_cents;
  if (toDeliver === null || toDeliver === undefined) return null;
  const toInvoice = overview?.to_invoice_cents ?? 0;
  const open = [
    toDeliver > 0 ? `${formatEuro(toDeliver)} nog aan te leveren` : '',
    toInvoice > 0 ? `${formatEuro(toInvoice)} nog te factureren` : '',
  ].filter(Boolean);
  return {
    key: 'billing',
    text: 'Factureren',
    href: PATHS.billing,
    notice: ofScope(
      steering?.turnover?.scope,
      open.length > 0 ? `Nu ${open.join(', ')}` : 'Nu niets aan te leveren of te factureren',
    ),
  };
}

function yearAccountRow({ steering, overview }: MoneySources): LinkRow | null {
  if (!steering?.turnover && !hasFigures(overview?.figures_active)) return null;
  return { key: 'year', text: 'Jaarverantwoording', href: PATHS.yearAccount };
}

/**
 * One row per place the reader has something to read. A block the reader may
 * not see is absent from the response, and so is its row.
 */
export function moneyRows(sources: MoneySources): LinkRow[] {
  return [
    assignmentsRow(sources),
    turnoverRow(sources),
    investmentRow(sources),
    potentialRow(sources),
    costsRow(sources),
    billingRow(sources),
    yearAccountRow(sources),
  ].filter((row): row is LinkRow => row !== null);
}
