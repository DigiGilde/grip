/**
 * Spread on the cells of a row whose cells differ in height (a long text
 * next to a date): every cell then starts at the top of the row instead of
 * floating in its middle. `<nldd-text-cell {...TOP_ALIGNED} />`.
 */
export const TOP_ALIGNED = { 'vertical-alignment': 'top' } as const;
