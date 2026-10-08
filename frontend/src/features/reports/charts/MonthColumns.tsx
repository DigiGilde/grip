import { useId, useState, type KeyboardEvent } from 'react';
import { monthAbbreviation, monthName } from '../labels';
import { niceAxis } from './scale';

const INK = 'var(--primitives-color-neutral-900)';
const MUTED = 'var(--primitives-color-neutral-650)';
const GRID = 'var(--primitives-color-neutral-150)';
const BAND = 'var(--primitives-color-neutral-50)';
const SURFACE = 'var(--semantics-surfaces-base-background-color)';

export interface ColumnSeries {
  key: string;
  label: string;
  color: string;
  /** One value per month, in the unit `formatValue` understands. */
  values: number[];
}

interface MonthColumnsProps {
  /** What the chart shows, for a screen reader and as the visible caption. */
  title: string;
  /** `YYYY-MM` per column. */
  months: string[];
  /** One series, or two that are stacked. The first sits on the baseline. */
  series: ColumnSeries[];
  formatValue: (value: number) => string;
  /** A horizontal line to read the columns against, e.g. 100 percent. */
  reference?: { value: number; label: string };
}

const WIDTH = 720;
const HEIGHT = 240;
const MARGIN = { top: 16, right: 12, bottom: 30, left: 78 };
const PLOT_WIDTH = WIDTH - MARGIN.left - MARGIN.right;
const PLOT_HEIGHT = HEIGHT - MARGIN.top - MARGIN.bottom;
const MAX_COLUMN_WIDTH = 24;
const GAP = 2;
const RADIUS = 4;

/** A column segment; only the one on top gets the rounded data end. */
function segmentPath(x: number, y: number, width: number, height: number, rounded: boolean) {
  if (!rounded || height < RADIUS) {
    return `M${x},${y}h${width}v${height}h${-width}z`;
  }
  return (
    `M${x},${y + height}v${-(height - RADIUS)}` +
    `a${RADIUS},${RADIUS} 0 0 1 ${RADIUS},${-RADIUS}` +
    `h${width - 2 * RADIUS}` +
    `a${RADIUS},${RADIUS} 0 0 1 ${RADIUS},${RADIUS}` +
    `v${height - RADIUS}z`
  );
}

/**
 * Columns per month, drawn as inline SVG. The table that goes with every
 * chart on the page holds the same values, so the chart never gates them:
 * it is the quick read, the table is the record.
 *
 * Pointer: hovering a month shows its values. Keyboard: the chart is one tab
 * stop, and the arrow keys walk the months; the values of the month in focus
 * are also announced.
 */
export function MonthColumns({ title, months, series, formatValue, reference }: MonthColumnsProps) {
  const [active, setActive] = useState<number | null>(null);
  const titleId = useId();
  const helpId = useId();

  const totals = months.map((_, index) =>
    series.reduce((sum, item) => sum + Math.max(0, item.values[index] ?? 0), 0),
  );
  const axis = niceAxis(Math.max(...totals, reference?.value ?? 0));
  const slot = PLOT_WIDTH / Math.max(1, months.length);
  const columnWidth = Math.min(MAX_COLUMN_WIDTH, slot * 0.6);
  const y = (value: number) => MARGIN.top + PLOT_HEIGHT - (value / axis.max) * PLOT_HEIGHT;
  const baseline = y(0);

  const readout = (index: number) =>
    `${monthName(months[index] ?? '')}: ` +
    series.map((item) => `${item.label} ${formatValue(item.values[index] ?? 0)}`).join(', ');

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (months.length === 0) return;
    const last = months.length - 1;
    let next: number | null = null;
    if (event.key === 'ArrowRight') next = active === null ? 0 : Math.min(last, active + 1);
    else if (event.key === 'ArrowLeft') next = active === null ? last : Math.max(0, active - 1);
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = last;
    else if (event.key === 'Escape') {
      setActive(null);
      return;
    }
    if (next !== null) {
      event.preventDefault();
      setActive(next);
    }
  };

  return (
    <figure style={{ margin: 0, maxWidth: `${WIDTH}px` }}>
      <figcaption id={titleId} style={{ fontWeight: 600, marginBottom: '4px' }}>
        {title}
      </figcaption>
      {series.length > 1 && (
        <ul
          aria-label="Legenda"
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            gap: '4px 16px',
            listStyle: 'none',
            margin: '0 0 4px',
            padding: 0,
            fontSize: '0.875rem',
          }}
        >
          {series.map((item) => (
            <li key={item.key} style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span
                aria-hidden="true"
                style={{
                  width: '12px',
                  height: '12px',
                  borderRadius: '2px',
                  background: item.color,
                  forcedColorAdjust: 'none',
                }}
              />
              {item.label}
            </li>
          ))}
        </ul>
      )}
      <div
        role="group"
        tabIndex={0}
        aria-labelledby={titleId}
        aria-describedby={helpId}
        onKeyDown={onKeyDown}
        onBlur={() => setActive(null)}
        onPointerLeave={() => setActive(null)}
        style={{ position: 'relative' }}
      >
        <svg
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          width="100%"
          aria-hidden="true"
          focusable="false"
          style={{ display: 'block', height: 'auto', overflow: 'visible' }}
        >
          {axis.ticks.map((tick) => (
            <g key={tick}>
              <line
                x1={MARGIN.left}
                x2={WIDTH - MARGIN.right}
                y1={y(tick)}
                y2={y(tick)}
                stroke={GRID}
                strokeWidth={1}
              />
              <text
                x={MARGIN.left - 8}
                y={y(tick)}
                dy="0.32em"
                textAnchor="end"
                fontSize={12}
                fill={MUTED}
                style={{ fontVariantNumeric: 'tabular-nums' }}
              >
                {formatValue(tick)}
              </text>
            </g>
          ))}
          {months.map((month, index) => {
            const left = MARGIN.left + index * slot;
            const x = left + (slot - columnWidth) / 2;
            // Only segments with something to show; the top one is rounded.
            const present = series
              .map((item) => ({ item, value: Math.max(0, item.values[index] ?? 0) }))
              .filter((segment) => segment.value > 0);
            let top = baseline;
            return (
              <g key={month} data-month={month}>
                {active === index && (
                  <rect x={left} y={MARGIN.top} width={slot} height={PLOT_HEIGHT} fill={BAND} />
                )}
                {present.map((segment, position) => {
                  const height = (segment.value / axis.max) * PLOT_HEIGHT;
                  // The gap between stacked segments is surface, not a stroke.
                  const drawn = Math.max(1, height - (position > 0 ? GAP : 0));
                  top -= height;
                  return (
                    <path
                      key={segment.item.key}
                      data-series={segment.item.key}
                      d={segmentPath(x, top, columnWidth, drawn, position === present.length - 1)}
                      fill={segment.item.color}
                    />
                  );
                })}
                <text
                  x={left + slot / 2}
                  y={HEIGHT - 10}
                  textAnchor="middle"
                  fontSize={12}
                  fill={MUTED}
                >
                  {monthAbbreviation(month)}
                </text>
                {/* The hit area is the whole slot, far bigger than the mark. */}
                <rect
                  x={left}
                  y={MARGIN.top}
                  width={slot}
                  height={PLOT_HEIGHT + MARGIN.bottom}
                  fill="transparent"
                  onPointerEnter={() => setActive(index)}
                  onPointerDown={() => setActive(index)}
                />
              </g>
            );
          })}
          <line
            x1={MARGIN.left}
            x2={WIDTH - MARGIN.right}
            y1={baseline}
            y2={baseline}
            stroke={MUTED}
            strokeWidth={1}
          />
          {reference && (
            <g pointerEvents="none">
              <line
                x1={MARGIN.left}
                x2={WIDTH - MARGIN.right}
                y1={y(reference.value)}
                y2={y(reference.value)}
                stroke={INK}
                strokeWidth={1}
              />
              <text
                x={WIDTH - MARGIN.right}
                y={y(reference.value) - 5}
                textAnchor="end"
                fontSize={12}
                fill={INK}
                stroke={SURFACE}
                strokeWidth={3}
                paintOrder="stroke"
              >
                {reference.label}
              </text>
            </g>
          )}
        </svg>
        {active !== null && months[active] !== undefined && (
          <div
            data-testid="chart-tooltip"
            style={{
              position: 'absolute',
              top: 0,
              left: `${((MARGIN.left + (active + 0.5) * slot) / WIDTH) * 100}%`,
              transform:
                active > months.length / 2 ? 'translateX(calc(-100% - 12px))' : 'translateX(12px)',
              background: SURFACE,
              color: INK,
              border: `1px solid ${GRID}`,
              borderRadius: '6px',
              padding: '6px 10px',
              fontSize: '0.875rem',
              pointerEvents: 'none',
              whiteSpace: 'nowrap',
              boxShadow: '0 2px 8px rgb(0 0 0 / 0.12)',
            }}
          >
            <div style={{ color: MUTED }}>{monthName(months[active])}</div>
            {series.map((item) => (
              <div key={item.key} style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span
                  aria-hidden="true"
                  style={{
                    width: '10px',
                    height: '2px',
                    background: item.color,
                    forcedColorAdjust: 'none',
                  }}
                />
                <strong style={{ fontVariantNumeric: 'tabular-nums' }}>
                  {formatValue(item.values[active] ?? 0)}
                </strong>
                <span style={{ color: MUTED }}>{item.label}</span>
              </div>
            ))}
          </div>
        )}
        <p
          id={helpId}
          style={{ margin: '4px 0 0', fontSize: '0.8125rem', color: MUTED }}
        >
          Dezelfde cijfers staan in de tabel hieronder. Met de pijltoetsen loop je de maanden langs.
        </p>
        <div
          aria-live="polite"
          style={{
            position: 'absolute',
            width: '1px',
            height: '1px',
            overflow: 'hidden',
            clipPath: 'inset(50%)',
            whiteSpace: 'nowrap',
          }}
        >
          {active !== null ? readout(active) : ''}
        </div>
      </div>
    </figure>
  );
}
