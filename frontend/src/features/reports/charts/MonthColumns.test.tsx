import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { SERIES_COLORS } from './colors';
import { MonthColumns } from './MonthColumns';

const MONTHS = ['2026-01', '2026-02', '2026-03'];
const SERIES = [
  { key: 'realised', label: 'Gerealiseerd', color: SERIES_COLORS.first, values: [100, 0, 0] },
  { key: 'forecast', label: 'Prognose', color: SERIES_COLORS.second, values: [50, 200, 0] },
];
const format = (value: number) => `${value} euro`;

function renderChart(series = SERIES) {
  return render(
    <MonthColumns title="Omzet per maand" months={MONTHS} series={series} formatValue={format} />,
  );
}

describe('MonthColumns', () => {
  it('names the chart and is one tab stop', () => {
    renderChart();
    const chart = screen.getByRole('group', { name: 'Omzet per maand' });
    expect(chart).toHaveAttribute('tabindex', '0');
    expect(chart).toHaveAccessibleDescription(/tabel hieronder/);
  });

  it('draws a segment only where there is a value', () => {
    const { container } = renderChart();
    const segments = (month: string) =>
      [...container.querySelectorAll(`g[data-month="${month}"] path`)].map((path) =>
        path.getAttribute('data-series'),
      );
    expect(segments('2026-01')).toEqual(['realised', 'forecast']);
    expect(segments('2026-02')).toEqual(['forecast']);
    expect(segments('2026-03')).toEqual([]);
  });

  it('has a legend for two series and none for one', () => {
    const two = renderChart();
    expect(two.getByRole('list', { name: 'Legenda' })).toHaveTextContent('GerealiseerdPrognose');
    two.unmount();
    const one = renderChart([SERIES[0]!]);
    expect(one.queryByRole('list', { name: 'Legenda' })).toBeNull();
  });

  it('shows and announces the values of the month the arrow keys reach', () => {
    renderChart();
    const chart = screen.getByRole('group', { name: 'Omzet per maand' });
    expect(screen.queryByTestId('chart-tooltip')).toBeNull();

    fireEvent.keyDown(chart, { key: 'ArrowRight' });
    expect(screen.getByTestId('chart-tooltip')).toHaveTextContent('januari 2026');
    expect(screen.getByTestId('chart-tooltip')).toHaveTextContent('100 euro');
    expect(chart.querySelector('[aria-live]')).toHaveTextContent(
      'januari 2026: Gerealiseerd 100 euro, Prognose 50 euro',
    );

    fireEvent.keyDown(chart, { key: 'ArrowRight' });
    expect(screen.getByTestId('chart-tooltip')).toHaveTextContent('februari 2026');
    fireEvent.keyDown(chart, { key: 'End' });
    expect(screen.getByTestId('chart-tooltip')).toHaveTextContent('maart 2026');
    fireEvent.keyDown(chart, { key: 'ArrowRight' });
    expect(screen.getByTestId('chart-tooltip')).toHaveTextContent('maart 2026');

    fireEvent.keyDown(chart, { key: 'Escape' });
    expect(screen.queryByTestId('chart-tooltip')).toBeNull();
  });

  it('labels the axis with clean values and the reference line', () => {
    const { container } = render(
      <MonthColumns
        title="Bezetting per maand"
        months={MONTHS}
        series={[{ key: 'pct', label: 'Bezetting', color: SERIES_COLORS.first, values: [40, 90, 120] }]}
        formatValue={(value) => `${value}%`}
        reference={{ value: 100, label: '100%' }}
      />,
    );
    const texts = [...container.querySelectorAll('svg text')].map((text) => text.textContent);
    expect(texts).toContain('0%');
    expect(texts).toContain('150%');
    expect(texts).toContain('jan');
    expect(texts.filter((text) => text === '100%')).toHaveLength(2);
  });

  it('never lets a label wear the series colour', () => {
    const { container } = renderChart();
    for (const text of container.querySelectorAll('svg text')) {
      expect(text.getAttribute('fill')).not.toContain('hemelblauw');
      expect(text.getAttribute('fill')).not.toContain('donkergeel');
    }
  });
});
