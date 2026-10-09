/** A passage a person still has to fill, as a standard text marks it. */
export const OPEN_PLACE = /\[vul aan:[^\]\n]*\]/g;

/**
 * The open place to go to next: the first one that starts at or after the
 * caret, or the first of the text when none follows. Counting presses would
 * skip a place each time one is filled, because the list gets shorter.
 */
export function nextOpenPlace(text: string, caret: number): { start: number; end: number } | null {
  const places = [...text.matchAll(OPEN_PLACE)].map((match) => ({
    start: match.index,
    end: match.index + match[0].length,
  }));
  if (places.length === 0) return null;
  return places.find((place) => place.start >= caret) ?? places[0] ?? null;
}
