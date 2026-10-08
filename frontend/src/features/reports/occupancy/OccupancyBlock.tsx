import { useMemo, useState } from 'react';
import { assignmentPath } from '@/features/assignments/paths';
import { Button } from '@/features/assignments/ui';
import { Segments } from '@/features/team/ui/controls';
import { RouterLinks } from '@/layout/RouterLinks';
import { formatPercent } from '@/lib/format';
import type { Occupancy, OccupancyCell, PersonOccupancy } from '../api';
import { scopeNote } from '../labels';
import { Figures, ReportBlock } from '../ui';
import { occupancyFigures } from './figures';
import { HeatCell, Heatmap, type CellRef } from './Heatmap';
import {
  cellTitle,
  describeCell,
  hasInzet,
  partTags,
  sortPersons,
  type SortMode,
} from './model';

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

/** What one cell consists of: the parts per assignment, firm or tentative. */
function CellDetail({
  person,
  cell,
  onClose,
}: {
  person: PersonOccupancy;
  cell: OccupancyCell;
  onClose: () => void;
}) {
  const parts = cell.parts ?? [];
  return (
    <div className="grip-occ__detail" data-testid="occupancy-detail">
      <h4>
        {cellTitle(person, cell)}: <span className="grip-occ__detail-total">{describeCell(cell)}</span>
      </h4>
      {parts.length > 0 && (
        <RouterLinks>
          <ul>
            {parts.map((part, index) => (
              <li key={part.assignment_id ?? index}>
                {part.assignment_id && part.assignment_name ? (
                  <nldd-link href={assignmentPath(part.assignment_id)} text={part.assignment_name} />
                ) : (
                  'Een opdracht die je niet mag inzien'
                )}
                : <strong>{formatPercent(part.pct)}</strong>, {partTags(part).join(', ')}
              </li>
            ))}
          </ul>
        </RouterLinks>
      )}
      <div style={{ marginTop: '8px' }}>
        <Button text="Sluit" size="xs" appearance="neutral-transparent" onClick={onClose} />
      </div>
    </div>
  );
}

/**
 * Occupancy: who has room and who is overbooked. The figures say it first,
 * the heat map shows where, and a cell opens what it consists of.
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
  const [sort, setSort] = useState<SortMode>('problems');
  const [selected, setSelected] = useState<CellRef | null>(null);
  const [showLeftOut, setShowLeftOut] = useState(false);
  const [showBench, setShowBench] = useState(false);

  // People with inzet are the table. Whoever is deployable but has no inzet
  // in the whole year would be a row of empty cells: they are counted in a
  // line below and shown on request, at the bottom.
  const { persons, bench } = useMemo(() => {
    const all = occupancy.persons ?? [];
    const idle = sortPersons(all.filter((person) => !hasInzet(person)), 'name');
    const busy = sortPersons(all.filter(hasInzet), sort);
    return { persons: showBench ? [...busy, ...idle] : busy, bench: idle };
  }, [occupancy.persons, sort, showBench]);
  const leftOut = occupancy.not_deployable ?? [];
  const selectedPerson = selected
    ? persons.find((person) => person.person_id === selected.personId)
    : undefined;
  const selectedCell = selectedPerson?.cells.find((cell) => cell.month === selected?.month);

  return (
    <ReportBlock
      bare={bare}
      testId="occupancy"
      title="Bezetting"
      note={scopeNote(
        occupancy.scope,
        `Iedereen die in ${year} inzetbaar is. Beschikbaar is 1 FTE per persoon per maand.`,
        `Alleen de personen van wie je de inzet mag zien. Beschikbaar is 1 FTE per persoon per maand.`,
      )}
    >
      <Figures label="Bezetting in het kort" figures={occupancyFigures(occupancy.summary, year)} />
      <nldd-container layout="wrap" gap="12" vertical-alignment="center">
        <Segments
          label="Volgorde van de personen"
          value={sort}
          onChange={(next) => setSort(next === 'name' ? 'name' : 'problems')}
          options={[
            { value: 'problems', label: 'Knelpunten eerst' },
            { value: 'name', label: 'Op naam' },
          ]}
        />
        <nldd-text size="sm" color="secondary">
          {sort === 'problems'
            ? 'Bovenaan wie boven 100% zit, daarna wie de meeste ruimte heeft.'
            : 'Op alfabet.'}
        </nldd-text>
      </nldd-container>
      <div className="grip-occ">
        <nldd-container gap="8">
          <Heatmap
            label={`Bezetting per persoon en maand in ${year}, in procenten`}
            persons={persons}
            months={occupancy.months ?? []}
            currentMonth={occupancy.summary.current_month}
            selected={selected}
            onSelect={setSelected}
          />
          <Legend />
          <div aria-live="polite">
            {selectedPerson && selectedCell ? (
              <CellDetail
                person={selectedPerson}
                cell={selectedCell}
                onClose={() => setSelected(null)}
              />
            ) : (
              <nldd-text size="sm" color="secondary">
                Kies een cel om te zien waaruit het percentage bestaat. Met de pijltoetsen loop je
                door de tabel, met Enter open je een cel.
              </nldd-text>
            )}
          </div>
        </nldd-container>
      </div>
      {bench.length > 0 && (
        <nldd-container
          layout="wrap"
          gap="8"
          vertical-alignment="center"
          data-testid="occupancy-bench"
        >
          <nldd-text size="sm">
            {bench.length === 1
              ? `1 persoon is inzetbaar maar heeft in ${year} geen inzet.`
              : `${bench.length} mensen zijn inzetbaar maar hebben in ${year} geen inzet.`}
          </nldd-text>
          <Button
            text={showBench ? 'Haal ze uit de tabel' : 'Toon ze in de tabel'}
            size="xs"
            appearance="neutral-transparent"
            onClick={() => setShowBench((shown) => !shown)}
          />
        </nldd-container>
      )}
      {leftOut.length > 0 && (
        <nldd-container gap="4" data-testid="occupancy-left-out">
          <nldd-container layout="wrap" gap="8" vertical-alignment="center">
            <nldd-text size="sm">
              {leftOut.length === 1
                ? `1 persoon staat er niet in: zonder inzetschaal en zonder inzet in ${year}.`
                : `${leftOut.length} mensen staan er niet in: zij hebben in ${year} geen inzetschaal en geen inzet.`}
            </nldd-text>
            <Button
              text={showLeftOut ? 'Verberg wie' : 'Toon wie'}
              size="xs"
              appearance="neutral-transparent"
              onClick={() => setShowLeftOut((shown) => !shown)}
            />
          </nldd-container>
          {showLeftOut && (
            <nldd-text size="sm" color="secondary">
              {leftOut.map((person) => person.person_name).join(', ')}
            </nldd-text>
          )}
        </nldd-container>
      )}
    </ReportBlock>
  );
}
