import { Fragment, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { assignmentPath } from '@/features/assignments/paths';
import { RouterLinks } from '@/layout/RouterLinks';
import { formatPercent } from '@/lib/format';
import { ActionBar } from '@/ui/ActionBar';
import { EmptyNotice, Quiet } from '@/ui/layout';
import type { Occupancy, OccupancyCell, PersonOccupancy } from '../api';
import { monthName, scopeNote } from '../labels';
import { ReportBlock } from '../ui';
import { occupancyTiles, type OccupancyTile } from './figures';
import { HeatCell, Heatmap, type CellRef } from './Heatmap';
import { cellTitle, freeSummary, partStanding, sortPersons, type SortMode } from './model';
import { cellState } from './scale';
import { groupPersons, sameGroup, useOccupancyView, type Groups, type Show } from './view';

const LEGEND_CELL = { month: '', available: true, tentative_pct: '0', established: false, parts: [] };

function Legend() {
  const sample = (cell: Partial<OccupancyCell>): OccupancyCell => ({ ...LEGEND_CELL, pct: '0', ...cell });
  const items: [OccupancyCell, string][] = [
    [sample({ pct: '25' }), '1 tot 25%'],
    [sample({ pct: '50' }), 'tot 50%'],
    [sample({ pct: '75' }), 'tot 75%'],
    [sample({ pct: '100' }), 'tot 100%'],
    [sample({ pct: '120' }), 'boven 100%'],
    [sample({ pct: '80', tentative_pct: '80' }), 'onder voorbehoud (gestreept)'],
    [sample({ pct: '50', established: true }), 'vastgesteld (stip)'],
    [sample({}), 'geen inzet'],
    [sample({ available: false }), 'niet inzetbaar'],
  ];
  return (
    <ul className="grip-occ__legend" aria-label="Legenda van de bezetting">
      {items.map(([cell, text]) => (
        <li key={text}>
          <span aria-hidden="true">
            <HeatCell cell={cell} />
          </span>
          {text}
        </li>
      ))}
    </ul>
  );
}

/** One figure. With rows behind it, it is the link that shows them. */
function TileView({
  tile,
  to,
  current,
  onFollow,
}: {
  tile: OccupancyTile;
  to: string | null;
  current: boolean;
  onFollow: () => void;
}) {
  const className = [
    'grip-tile',
    tile.attention ? 'grip-tile--attention' : '',
    tile.quiet ? 'grip-tile--quiet' : '',
  ]
    .filter(Boolean)
    .join(' ');
  const content = (
    <>
      <span className="grip-tile__label">{tile.label}</span>
      <span className="grip-tile__value">{tile.value}</span>
      {tile.attention && (
        <span className="grip-tile__flag" style={{ marginTop: 0 }}>
          <span className="grip-mark" aria-hidden="true">
            !
          </span>
          {tile.attention}
        </span>
      )}
      {tile.months && tile.months.length > 0 && (
        <dl className="grip-tile__months">
          {tile.months.map((month) => (
            <div key={month.label}>
              <dt>{month.label}</dt>
              <dd>{month.value}</dd>
            </div>
          ))}
        </dl>
      )}
      {tile.detail && <span className="grip-tile__context">{tile.detail}</span>}
    </>
  );
  if (to === null) {
    return (
      <div className={className} data-testid={`occupancy-tile-${tile.key}`}>
        {content}
      </div>
    );
  }
  return (
    <Link
      to={{ search: to }}
      className={className}
      data-testid={`occupancy-tile-${tile.key}`}
      aria-current={current ? 'true' : undefined}
      onClick={onFollow}
    >
      {content}
    </Link>
  );
}

/**
 * What a cell consists of, as one sentence: "130% ingepland: 100% vast op
 * Opdracht Alfa, 30% onder voorbehoud op Opdracht Beta."
 */
function CellDetail({ person, cell }: { person: PersonOccupancy; cell: OccupancyCell }) {
  const parts = cell.parts ?? [];
  const state = cellState(cell.available, Number(cell.pct));
  return (
    <div className="grip-occ__detail" data-testid="occupancy-detail">
      <h4>{cellTitle(person, cell)}</h4>
      <RouterLinks>
        <p>
          {state === 'unavailable' && 'Niet inzetbaar in deze maand.'}
          {state === 'empty' && 'Geen inzet in deze maand.'}
          {(state === 'filled' || state === 'over') && (
            <>
              <span className="grip-occ__detail-total">{formatPercent(cell.pct)} ingepland</span>
              {parts.length > 0 && ': '}
              {parts.map((part, index) => (
                <Fragment key={part.assignment_id ?? index}>
                  {index > 0 && ', '}
                  {formatPercent(part.pct)} {partStanding(part)} op{' '}
                  {part.assignment_id && part.assignment_name ? (
                    <nldd-link href={assignmentPath(part.assignment_id)} text={part.assignment_name} />
                  ) : (
                    'een opdracht die je niet mag inzien'
                  )}
                </Fragment>
              ))}
              .
            </>
          )}
        </p>
      </RouterLinks>
    </div>
  );
}

const SHOW_LABELS: Record<Show, (year: number, now: string) => string> = {
  'met-inzet': (year) => `Met inzet in ${year}`,
  'zonder-inzet': () => 'Zonder inzet de komende 3 maanden',
  'boven-100': () => 'Boven 100%',
  vrij: (_year, now) => (now ? `Met ruimte in ${monthName(now)}` : 'Met ruimte nu'),
  'zonder-inzet-jaar': (year) => `Zonder inzet in ${year}`,
  iedereen: () => 'Iedereen',
};

/**
 * The groups on offer in the filter. "Zonder inzet in het jaar" is its own
 * choice only when it is not the same people as "zonder inzet de komende 3
 * maanden"; when it is, the fact is said once.
 */
function showOptions(groups: Groups, year: number, now: string) {
  const order: Show[] = ['met-inzet', 'zonder-inzet', 'boven-100', 'vrij', 'zonder-inzet-jaar', 'iedereen'];
  const yearIsAhead = sameGroup(groups['zonder-inzet-jaar'], groups['zonder-inzet']);
  return order
    .filter((show) => show !== 'zonder-inzet-jaar' || (!yearIsAhead && groups[show].length > 0))
    .map((show) => ({
      value: show,
      label: `${SHOW_LABELS[show](year, now)} (${groups[show].length})`,
    }));
}

const SORT_OPTIONS: { value: SortMode; label: string }[] = [
  { value: 'problems', label: 'Knelpunten eerst' },
  { value: 'free', label: 'Meeste ruimte nu eerst' },
  { value: 'name', label: 'Op naam' },
];

/**
 * Occupancy: who has room and who is overbooked. The figures say it first
 * and each one opens the people it counts; the heat map shows where; a cell
 * opens what it consists of. Which people are shown is in the address.
 */
export function OccupancyBlock({
  occupancy,
  year,
  bare,
}: {
  occupancy: Occupancy;
  year: number;
  bare?: boolean;
}) {
  const all = useMemo(() => occupancy.persons ?? [], [occupancy.persons]);
  const groups = useMemo(() => groupPersons(all), [all]);
  const view = useOccupancyView(groups);
  // The cell someone opened, remembered with the view it was opened in: a
  // new view (another group, another month in the address) starts fresh.
  const [picked, setPicked] = useState<{ view: string; cell: CellRef | null } | null>(null);
  const [focusRequest, setFocusRequest] = useState(0);

  const now = occupancy.summary.current_month;
  const persons = useMemo(
    () => sortPersons(groups[view.show], view.sort),
    [groups, view.show, view.sort],
  );
  const tiles = occupancyTiles(occupancy.summary, year, groups);
  const leftOut = occupancy.not_deployable ?? [];

  // A month in the address (the figure "boven 100%" puts it there) opens
  // the first row that has something to show in that month, until someone
  // opens or closes a cell themselves.
  const viewKey = `${view.show}|${view.month ?? ''}`;
  const fromAddress = useMemo<CellRef | null>(() => {
    if (!view.month) return null;
    const person =
      persons.find((row) => row.over_months?.includes(view.month ?? '')) ?? persons[0];
    return person && person.cells.some((cell) => cell.month === view.month)
      ? { personId: person.person_id, month: view.month }
      : null;
  }, [persons, view.month]);
  const selected = picked && picked.view === viewKey ? picked.cell : fromAddress;
  const setSelected = (cell: CellRef | null) => setPicked({ view: viewKey, cell });

  const selectedPerson = selected
    ? persons.find((person) => person.person_id === selected.personId)
    : undefined;
  const selectedCell = selectedPerson?.cells.find((cell) => cell.month === selected?.month);
  const filtered = view.show !== view.fallback && view.show !== 'iedereen';

  return (
    <ReportBlock
      bare={bare}
      testId="occupancy"
      title="Bezetting"
      note={scopeNote(
        occupancy.scope,
        `Iedereen die in ${year} inzetbaar is.`,
        'Alleen de personen van wie je de inzet mag zien.',
      )}
    >
      <ul className="grip-tiles grip-tiles--compact" aria-label="Bezetting in het kort">
        {tiles.map((tile) => (
          <li key={tile.key}>
            <TileView
              tile={tile}
              to={tile.target ? view.searchFor(tile.target) : null}
              current={tile.target !== undefined && tile.target.show === view.show}
              onFollow={() => {
                // A figure that points at a month also moves the keyboard there.
                if (tile.target?.month) setFocusRequest((request) => request + 1);
              }}
            />
          </li>
        ))}
      </ul>
      <ActionBar
        label="Bezetting filteren"
        filters={[
          {
            label: 'Toon',
            value: view.show,
            onChange: (next) => view.go({ show: next as Show, sort: view.sort }),
            options: showOptions(groups, year, now),
            width: '320px',
          },
          {
            label: 'Volgorde',
            value: view.sort,
            onChange: (next) => view.go({ show: view.show, sort: next as SortMode }),
            options: SORT_OPTIONS,
            width: '220px',
          },
        ]}
        actions={filtered ? [{ text: 'Toon iedereen', onClick: () => view.go({ show: 'iedereen' }) }] : []}
      />
      {persons.length === 0 ? (
        <EmptyNotice text="Niemand in deze groep" />
      ) : (
        <div className="grip-occ">
          <nldd-container gap="8">
            <Heatmap
              label={`Bezetting per persoon en maand in ${year}, in procenten`}
              persons={persons}
              months={occupancy.months ?? []}
              currentMonth={now}
              selected={selected}
              onSelect={setSelected}
              rowNote={(person) => freeSummary(person, view.show === 'vrij')}
              focusRequest={focusRequest}
            />
            <div aria-live="polite">
              {selectedPerson && selectedCell && (
                <CellDetail person={selectedPerson} cell={selectedCell} />
              )}
            </div>
            <Legend />
            <Quiet>
              Beschikbaar is 1 FTE per persoon per maand. Een naam opent het inzetbord van die
              persoon, een cel laat zien waaruit het percentage bestaat.
            </Quiet>
          </nldd-container>
        </div>
      )}
      {leftOut.length > 0 && (
        <details className="grip-disclosure" data-testid="occupancy-left-out">
          <summary>
            {leftOut.length === 1
              ? `1 persoon staat er niet in: zonder inzetschaal en zonder inzet in ${year}`
              : `${leftOut.length} mensen staan er niet in: zonder inzetschaal en zonder inzet in ${year}`}
          </summary>
          <Quiet>{leftOut.map((person) => person.person_name).join(', ')}</Quiet>
        </details>
      )}
    </ReportBlock>
  );
}
