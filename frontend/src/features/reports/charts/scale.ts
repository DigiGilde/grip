/**
 * A value axis with clean tick values: 0, 50, 100 rather than 0, 47, 94.
 * Presentation only; no amount is computed here.
 */
export interface Axis {
  /** The top of the axis, a tick value at or above the largest value. */
  max: number;
  ticks: number[];
}

const STEPS = [1, 2, 2.5, 5, 10];

export function niceAxis(largest: number, maxTicks = 5): Axis {
  if (!Number.isFinite(largest) || largest <= 0) return { max: 1, ticks: [0, 1] };
  const rough = largest / (maxTicks - 1);
  const magnitude = 10 ** Math.floor(Math.log10(rough));
  const step = (STEPS.find((candidate) => candidate * magnitude >= rough) ?? 10) * magnitude;
  const count = Math.ceil(largest / step - 1e-9);
  const ticks = Array.from({ length: count + 1 }, (_, index) => index * step);
  return { max: count * step, ticks };
}
