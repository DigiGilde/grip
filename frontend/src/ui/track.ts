/** Where a row stands on a track of `nldd-step-cell`: decides on which sides the line runs. */
export type TrackPlace = 'first' | 'between' | 'last' | 'only';

export function placeOf(index: number, count: number): TrackPlace {
  if (count === 1) return 'only';
  if (index === 0) return 'first';
  return index === count - 1 ? 'last' : 'between';
}
