/**
 * The restricted text grip stores, and what an editor may put in it.
 *
 * A text of a quote or a vacancy is plain text with a few marks, a subset of
 * markdown: a blank line between paragraphs, "- " for a list item, "1. " for
 * a numbered item, "## " or "### " for a heading, "**strong**" and
 * "*emphasis*". It is stored as that text, so what is signed or published is
 * the text itself. The server decides what the marks mean; this module only
 * keeps what a person writes inside the set a given text allows.
 *
 * Two texts use the form, with different sets:
 *   - a vacancy text: "## " starts a section; lists and emphasis, nothing else;
 *   - a section of a quote: "### " is a small heading; lists, numbered lists,
 *     strong and emphasis.
 */

export interface TextMarks {
  /** The one heading level this text knows, or none. */
  heading: 2 | 3 | null;
  /** Whether "1. " makes a numbered list; otherwise it becomes a plain list. */
  numbered: boolean;
  /** Whether "**strong**" exists; otherwise it becomes emphasis. */
  strong: boolean;
}

/** A whole vacancy text: sections under "## ". */
export const VACANCY_TEXT_MARKS: TextMarks = { heading: 2, numbered: false, strong: false };
/** The body of one section of a vacancy text; its heading is a field of its own. */
export const VACANCY_SECTION_MARKS: TextMarks = { heading: null, numbered: false, strong: false };
/** A section of a quote, and a standard text block of a quote. */
export const QUOTE_SECTION_MARKS: TextMarks = { heading: 3, numbered: true, strong: true };

const HEADING = /^\s{0,3}#{1,6}\s+(.*)$/;
const BULLET = /^\s*(?:[-*+•])\s+(?:\[[ xX]\]\s+)?(.*)$/;
const NUMBERED = /^\s*(\d{1,3})[.)]\s+(.*)$/;
const QUOTED = /^\s*>\s?(.*)$/;

function inline(text: string, marks: TextMarks): string {
  let out = text
    // A link keeps its words and its address, as text.
    .replace(/\[([^\]\n]+)\]\((\S+?)\)/g, '$1 ($2)')
    .replace(/~~(?=\S)(.+?)(?<=\S)~~/g, '$1')
    .replace(/`([^`\n]+)`/g, '$1')
    .replace(/__(?=\S)(.+?)(?<=\S)__/g, '**$1**')
    .replace(/(?<![\w_])_(?=\S)([^_\n]+?)(?<=\S)_(?![\w_])/g, '*$1*');
  if (!marks.strong) out = out.replace(/\*\*(?=\S)(.+?)(?<=\S)\*\*/g, '*$1*');
  return out;
}

/**
 * What an editor holds, as the text to store: every mark the text does not
 * know becomes the nearest one it does, or plain text. A text that is already
 * in its stored form comes back unchanged.
 */
export function toStored(text: string, marks: TextMarks): string {
  return text
    .replace(/\r\n?/g, '\n')
    .split('\n')
    .map((line) => {
      const heading = HEADING.exec(line);
      if (heading) {
        const words = inline(heading[1] ?? '', marks);
        return marks.heading ? `${'#'.repeat(marks.heading)} ${words}` : words;
      }
      const numbered = NUMBERED.exec(line);
      if (numbered) {
        const words = inline(numbered[2] ?? '', marks);
        return marks.numbered ? `${numbered[1]}. ${words}` : `- ${words}`;
      }
      const bullet = BULLET.exec(line);
      if (bullet) return `- ${inline(bullet[1] ?? '', marks)}`;
      const quoted = QUOTED.exec(line);
      return inline(quoted ? (quoted[1] ?? '') : line, marks);
    })
    .join('\n');
}

export interface OpenPlace {
  /** Offsets in the text. */
  start: number;
  end: number;
  /** What still has to be filled in, without the brackets. */
  what: string;
}

/** The passages a standard text leaves for a person: "[vul aan: ...]". */
export function openPlaces(text: string): OpenPlace[] {
  return [...text.matchAll(/\[vul aan:\s*([^\]\n]*)\]/g)].map((match) => ({
    start: match.index,
    end: match.index + match[0].length,
    what: (match[1] ?? '').trim(),
  }));
}

export type Inline = { text: string; mark?: 'strong' | 'em' | 'open' };

export type Block =
  | { kind: 'heading'; level: 2 | 3; text: string }
  | { kind: 'paragraph'; lines: Inline[][] }
  | { kind: 'list'; ordered: boolean; items: Inline[][] };

/** A line as runs of plain, strong and emphasised text, and passages still to fill. */
export function inlineRuns(text: string): Inline[] {
  const runs: Inline[] = [];
  const pattern =
    /(\[vul aan:[^\]\n]*\])|\*\*(?=\S)(.+?)(?<=\S)\*\*|(?<![*\w])\*(?=\S)(.+?)(?<=\S)\*(?![*\w])/g;
  let at = 0;
  for (const match of text.matchAll(pattern)) {
    if (match.index > at) runs.push({ text: text.slice(at, match.index) });
    if (match[1] !== undefined) runs.push({ text: match[1], mark: 'open' });
    else if (match[2] !== undefined) runs.push({ text: match[2], mark: 'strong' });
    else runs.push({ text: match[3] ?? '', mark: 'em' });
    at = match.index + match[0].length;
  }
  if (at < text.length) runs.push({ text: text.slice(at) });
  return runs;
}

/** The stored text as blocks, the way it reads: headings, paragraphs and lists. */
export function textBlocks(text: string): Block[] {
  const blocks: Block[] = [];
  let paragraph: Inline[][] | null = null;
  let list: { ordered: boolean; items: Inline[][] } | null = null;
  const close = () => {
    if (paragraph) blocks.push({ kind: 'paragraph', lines: paragraph });
    if (list) blocks.push({ kind: 'list', ...list });
    paragraph = null;
    list = null;
  };
  for (const line of text.replace(/\r\n?/g, '\n').split('\n')) {
    if (!line.trim()) {
      close();
      continue;
    }
    const heading = /^\s*(#{2,3})\s+(.*)$/.exec(line);
    if (heading) {
      close();
      blocks.push({
        kind: 'heading',
        level: heading[1] === '##' ? 2 : 3,
        text: (heading[2] ?? '').trim(),
      });
      continue;
    }
    const numbered = /^\s*\d{1,3}[.)]\s+(.*)$/.exec(line);
    const bullet = numbered ? null : /^\s*[-•]\s+(.*)$/.exec(line);
    const item = numbered ?? bullet;
    if (item) {
      const ordered = numbered !== null;
      if (paragraph || (list && list.ordered !== ordered)) close();
      list ??= { ordered, items: [] };
      list.items.push(inlineRuns(item[1] ?? ''));
      continue;
    }
    if (list) close();
    paragraph ??= [];
    paragraph.push(inlineRuns(line));
  }
  close();
  return blocks;
}
