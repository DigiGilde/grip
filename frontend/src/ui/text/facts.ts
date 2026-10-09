/**
 * Facts in a text: what grip knows about the thing the text is for.
 *
 * A draft names a fact by key between braces ("{schaal}"), so the text
 * follows the fact until it is settled. The server decides which keys exist
 * and what they stand for; this module only finds them in a text and shows
 * the text as it reads.
 */
import { OPEN_PLACE } from './openPlaces';

export interface TextFact {
  key: string;
  /** "Schaal". */
  label: string;
  /** Null while it is not known. */
  value: string | null;
  /** "uit de aanvraag: Schaal". */
  source: string;
  /** Where it is filled: the request, the settings or the sender. */
  where: 'request' | 'settings' | 'sender';
  /** "Vul de schaal in op de aanvraag". */
  instruction: string;
}

const FACT_PLACE = /\{([a-z_]+)\}/g;

export interface FactPlace {
  start: number;
  end: number;
  fact: TextFact;
}

/** Every place in the text that names one of these facts. */
export function factPlaces(text: string, facts: readonly TextFact[]): FactPlace[] {
  const byKey = new Map(facts.map((fact) => [fact.key, fact]));
  const places: FactPlace[] = [];
  for (const match of text.matchAll(FACT_PLACE)) {
    const fact = byKey.get(match[1] ?? '');
    if (fact) places.push({ start: match.index, end: match.index + match[0].length, fact });
  }
  return places;
}

/** The facts the text names that are not known yet, each once. */
export function unknownFacts(text: string, facts: readonly TextFact[]): TextFact[] {
  const found = new Map<string, TextFact>();
  for (const place of factPlaces(text, facts)) {
    if (place.fact.value === null) found.set(place.fact.key, place.fact);
  }
  return [...found.values()];
}

/** The text as it reads now: a fact by its value, an unknown one as an open place. */
export function withFacts(text: string, facts: readonly TextFact[]): string {
  const byKey = new Map(facts.map((fact) => [fact.key, fact]));
  return text.replace(FACT_PLACE, (whole, key: string) => {
    const fact = byKey.get(key);
    if (!fact) return whole;
    return fact.value ?? `[vul aan: ${fact.instruction}]`;
  });
}

export interface PlaceToFill {
  start: number;
  end: number;
  /** A passage a person writes, or a fact to fill in elsewhere. */
  kind: 'prose' | 'fact';
  /** What is asked, in words. */
  what: string;
  /** The place as it stands in the text. */
  text: string;
}

/** What still has to be done before the text is finished, in reading order. */
export function placesToFill(text: string, facts: readonly TextFact[]): PlaceToFill[] {
  const prose: PlaceToFill[] = [...text.matchAll(OPEN_PLACE)].map((match) => ({
    start: match.index,
    end: match.index + match[0].length,
    kind: 'prose',
    what: match[0].slice('[vul aan:'.length, -1).trim(),
    text: match[0],
  }));
  const unknown: PlaceToFill[] = factPlaces(text, facts)
    .filter((place) => place.fact.value === null)
    .map((place) => ({
      start: place.start,
      end: place.end,
      kind: 'fact',
      what: place.fact.instruction,
      text: text.slice(place.start, place.end),
    }));
  return [...prose, ...unknown].sort((a, b) => a.start - b.start);
}

/**
 * The place to go to next: the first one that starts at or after the caret,
 * or the first of the text when none follows.
 */
export function nextPlaceToFill(
  text: string,
  facts: readonly TextFact[],
  caret: number,
): PlaceToFill | null {
  const places = placesToFill(text, facts);
  return places.find((place) => place.start >= caret) ?? places[0] ?? null;
}
