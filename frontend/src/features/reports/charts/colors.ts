/**
 * The two chart colours, from the design system's palette. Step 500 has the
 * same value in light and dark mode, and the pair was checked with the
 * palette validator against both surfaces: lightness band, chroma floor,
 * separation under protanopia and deuteranopia (24), normal vision (26) and
 * contrast against the surface (at least 3:1). Neither is a status colour.
 */
export const SERIES_COLORS = {
  first: 'var(--primitives-color-hemelblauw-500)',
  second: 'var(--primitives-color-donkergeel-500)',
} as const;
