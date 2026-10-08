/**
 * How a percentage becomes a cell of the occupancy heat map.
 *
 * Fill: one hue, four steps, more is stronger (a sequential scale in bins).
 * The steps are from the design system's lintblauw ramp: 300, 450, 600 and
 * 750 in light mode; in dark mode the ramp mirrors itself, and the first
 * step is 350 instead of 300 so the lightest fill still stands off the dark
 * surface. Checked with the palette validator as an ordinal ramp against
 * both surfaces: lightness monotone, every step at least 0.06 apart, the
 * weakest fill at 2.5:1 (light) and 2.1:1 (dark) against the surface, one
 * hue. The number in a cell is neutral-950 on the first two steps and
 * neutral-0 on the last two: at least 4.6:1 in both modes.
 *
 * Above 100 percent is not a fifth step. It is a state: rood-600 with a
 * ring, a mark and bold type, so it reads without colour (6.2:1 for its
 * text in both modes). "Not deployable" is hatched, "deployable and empty"
 * is an outline. Tentative inzet is striped over its share of the cell and
 * an established month carries a dot: textures and shapes, not hues.
 */

/** unavailable: could not be deployed. empty: could, and has no inzet. */
export type CellState = 'unavailable' | 'empty' | 'filled' | 'over';

export type Level = 1 | 2 | 3 | 4;

/** The upper bound of each fill step, in percent. */
export const LEVEL_BOUNDS: readonly [number, number, number, number] = [25, 50, 75, 100];

export function cellState(available: boolean, pct: number): CellState {
  if (!available) return 'unavailable';
  if (pct <= 0) return 'empty';
  return pct > 100 ? 'over' : 'filled';
}

export function fillLevel(pct: number): Level {
  if (pct <= LEVEL_BOUNDS[0]) return 1;
  if (pct <= LEVEL_BOUNDS[1]) return 2;
  if (pct <= LEVEL_BOUNDS[2]) return 3;
  return 4;
}
