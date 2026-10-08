import { vi } from 'vitest';

/**
 * Answers fetch from a table of path prefixes, for render tests. A path that
 * is not in the table answers 404, so a screen that asks for something
 * unexpected shows up as an error state.
 */
export function mockApi(routes: Record<string, unknown>) {
  const calls: string[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    calls.push(url);
    const path = url.split('?')[0] ?? url;
    if (path in routes) {
      return new Response(JSON.stringify(routes[path]), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }
    return new Response(JSON.stringify({ title: 'Niet gevonden', status: 404 }), {
      status: 404,
      headers: { 'Content-Type': 'application/problem+json' },
    });
  });
  vi.stubGlobal('fetch', fetchMock);
  return { calls };
}

/** The `text` attributes of the given elements: what the user reads there. */
export function texts(container: ParentNode, selector: string): string[] {
  return [...container.querySelectorAll(selector)].map((el) => el.getAttribute('text') ?? '');
}
