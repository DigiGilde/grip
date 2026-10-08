import type { Sender, TextBlock } from './api';

/** Lines of an address or of what an organisation is part of, as one field. */
export const toLines = (text: string): string[] =>
  text
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean);

export const fromLines = (lines: readonly string[]): string => lines.join('\n');

/** What a block is, in the words of the list. */
export function blockKind(block: TextBlock): string {
  if (block.with_costs) return 'Bedragen uit de begroting';
  if (block.body) return 'Standaardtekst';
  return block.draftable ? 'Schrijf je per offerte, concept mogelijk' : 'Schrijf je per offerte';
}

/** The contact person as one line; empty when nobody is set. */
export function contactLine(sender: Sender): string {
  const { name, role, email, phone } = sender.contact;
  const who = name && role ? `${name} (${role})` : name;
  return [who, email, phone].filter(Boolean).join(', ');
}

export function signatoryLine(sender: Sender): string {
  const { name, title } = sender.signatory;
  return [name, title].filter(Boolean).join(', ');
}

/** A key for a new block, from its heading: letters, digits and dashes. */
export function keyFromHeading(heading: string, taken: readonly string[]): string {
  const base =
    heading
      .toLowerCase()
      .normalize('NFD')
      .replace(/[̀-ͯ]/g, '')
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '')
      .slice(0, 32) || 'onderdeel';
  let key = base;
  let n = 2;
  while (taken.includes(key)) {
    key = `${base}-${n}`;
    n += 1;
  }
  return key;
}

/** The blocks with one moved a place up or down. */
export function moved<T>(items: readonly T[], index: number, step: -1 | 1): T[] {
  const target = index + step;
  if (target < 0 || target >= items.length) return [...items];
  const next = [...items];
  const [item] = next.splice(index, 1);
  if (item !== undefined) next.splice(target, 0, item);
  return next;
}
