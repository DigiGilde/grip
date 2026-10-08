import { formatEuro, formatFte, formatPercent } from '@/lib/format';
import type { Steering } from './api';
import { monthAbbreviation, monthName } from './labels';
import type { TopicSlug } from './topics';

export interface Tile {
  topic: TopicSlug;
  label: string;
  /** The one figure of the tile. */
  value: string;
  /** Against what, or as of when. */
  context: string;
  /** Only when it needs attention: what is the matter, in words. */
  attention?: string;
}

const count = (number: number, one: string, many: string) =>
  `${number} ${number === 1 ? one : many}`;

/**
 * The headline figures of the landing view, one per block the API sent. A
 * block the reader may not see is absent from the response, and so is its
 * tile; the others reflow.
 */
export function landingTiles(steering: Steering): Tile[] {
  const tiles: Tile[] = [];
  const { turnover, occupancy, pipeline, costs, billability, open_roles: openRoles } = steering;

  if (turnover) {
    const figures = turnover.figures;
    tiles.push({
      topic: 'omzet',
      label: 'Verwacht totaal',
      value: formatEuro(figures.expected_total_cents),
      context:
        `van ${formatEuro(figures.budgeted_cents)} begroot, ` +
        `${formatEuro(figures.realised_total_cents)} gerealiseerd`,
      ...(figures.overrun ? { attention: 'Boven de begroting' } : {}),
    });
  }

  if (occupancy) {
    const [now, ...ahead] = occupancy.summary.window ?? [];
    const over = occupancy.summary.over_count;
    tiles.push({
      topic: 'bezetting',
      label: now ? `Bezetting in ${monthName(now.month)}` : 'Bezetting',
      value: now?.pct === null || now === undefined ? 'Onbekend' : formatPercent(now.pct),
      context:
        ahead.length > 0
          ? `vrij: ${ahead
              .map((month) => `${monthAbbreviation(month.month)} ${formatFte(month.free_fte)}`)
              .join(', ')} FTE`
          : `van ${count(occupancy.summary.person_count, 'persoon', 'mensen')}`,
      ...(over > 0 ? { attention: `${count(over, 'persoon', 'mensen')} boven 100%` } : {}),
    });
  }

  if (pipeline) {
    const issued = (pipeline.statuses ?? []).find((status) => status.status === 'issued');
    tiles.push({
      topic: 'pijplijn',
      label: 'Offertes die wachten op akkoord',
      value: formatEuro(issued?.total_cents ?? 0),
      context:
        count(issued?.count ?? 0, 'offerte', 'offertes') +
        (turnover && turnover.pipeline_cents > 0
          ? `, ${formatEuro(turnover.pipeline_cents)} werk nog niet afgesproken`
          : ''),
    });
  }

  if (costs) {
    tiles.push({
      topic: 'kosten',
      label: 'Ongedekte kosten',
      value: formatEuro(costs.uncovered_cents),
      context: `van ${formatEuro(costs.forecast_cents)} kosten in ${steering.year}`,
      ...(costs.uncovered_cents > 0 ? { attention: 'Geen begrotingsregel dekt dit' } : {}),
    });
  }

  if (billability) {
    const below = billability.below_target_count;
    tiles.push({
      topic: 'declarabiliteit',
      label: 'Verwacht onder target',
      value: below === 0 ? 'Niemand' : count(below, 'persoon', 'mensen'),
      context: `van ${billability.with_target_count} met een target in ${steering.year}`,
      ...(below > 0 ? { attention: 'Haalt het target niet' } : {}),
    });
  }

  if (openRoles) {
    const roles = openRoles.roles ?? [];
    const withoutVacancy = roles.filter((role) => !role.vacancy_status).length;
    tiles.push({
      topic: 'open-rollen',
      label: 'Open rollen',
      value: `${formatFte(openRoles.unfilled_fte)} FTE`,
      context: count(roles.length, 'rol', 'rollen') + ' nog in te vullen',
      ...(withoutVacancy > 0
        ? { attention: `${count(withoutVacancy, 'rol', 'rollen')} zonder vacature` }
        : {}),
    });
  }
  return tiles;
}
