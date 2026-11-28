// The Pagefind index, loaded on first use, shared by the search page and the search window.

export interface PagefindResultData {
  url: string;
  excerpt: string;
  meta: { title?: string };
  filters: Record<string, string[]>;
}

export interface PagefindResponse {
  results: { data: () => Promise<PagefindResultData> }[];
  filters: Record<string, Record<string, number>>;
  totalFilters?: Record<string, Record<string, number>>;
}

export interface Pagefind {
  options: (options: Record<string, unknown>) => Promise<void>;
  search: (term: string | null, options?: Record<string, unknown>) => Promise<PagefindResponse | null>;
  filters: () => Promise<Record<string, Record<string, number>>>;
}

export const NO_INDEX = 'Zoeken werkt alleen in de gebouwde site.';

let pagefind: Pagefind | null = null;

/** Null when there is no index, as in `astro dev`. */
export async function loadPagefind(): Promise<Pagefind | null> {
  if (pagefind) return pagefind;
  try {
    // A runtime path, so the bundler leaves it alone: the index is written after the build.
    const path = '/pagefind/pagefind.js';
    const loaded = (await import(/* @vite-ignore */ path)) as Pagefind;
    await loaded.options({ excerptLength: 24 });
    pagefind = loaded;
  } catch {
    return null;
  }
  return pagefind;
}

/** Pagefind marks hits with <mark>; the text cell knows **bold**. */
export function excerptText(html: string): string {
  const doc = new DOMParser().parseFromString(`<p>${html}</p>`, 'text/html');
  return [...doc.body.firstChild!.childNodes]
    .map((node) => (node.nodeName === 'MARK' ? `**${node.textContent}**` : (node.textContent ?? '')))
    .join('')
    .replace(/\s+/g, ' ')
    .trim();
}

/** One result as a row of a navigation list: section, title and excerpt. */
export function resultRow(result: PagefindResultData): HTMLElement {
  const item = document.createElement('nldd-list-item');
  item.setAttribute('href', result.url);
  const cell = document.createElement('nldd-text-cell');
  const section = result.filters.onderdeel?.[0];
  if (section) cell.setAttribute('overline', section);
  cell.setAttribute('text', result.meta.title ?? result.url);
  cell.setAttribute('supporting-text', excerptText(result.excerpt));
  item.append(cell);
  return item;
}
