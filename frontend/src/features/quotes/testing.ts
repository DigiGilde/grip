/** Test helpers for the quote, signing and monthly close screens. */
import { vi } from 'vitest';

type Reply = unknown | { status: number; body: unknown };

function isError(reply: Reply): reply is { status: number; body: unknown } {
  return typeof reply === 'object' && reply !== null && 'status' in reply && 'body' in reply;
}

/**
 * Answers fetch from a table of path to JSON. A path without an entry
 * answers 404 as a problem document, the way the API does.
 */
export function mockApi(replies: Record<string, Reply>) {
  const calls: { url: string; method: string; body: unknown }[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = init?.method ?? 'GET';
    calls.push({
      url,
      method,
      body: typeof init?.body === 'string' ? JSON.parse(init.body) : (init?.body ?? null),
    });
    const reply = replies[`${method} ${url}`] ?? replies[url];
    if (reply === undefined) {
      return new Response(JSON.stringify({ title: 'Niet gevonden', detail: 'Niet gevonden' }), {
        status: 404,
        headers: { 'Content-Type': 'application/problem+json' },
      });
    }
    if (isError(reply)) {
      return new Response(JSON.stringify(reply.body), {
        status: reply.status,
        headers: { 'Content-Type': 'application/problem+json' },
      });
    }
    return new Response(JSON.stringify(reply), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  });
  vi.stubGlobal('fetch', fetchMock);
  return { calls };
}

/** The `text` attribute of every matching element, in document order. */
export function texts(root: ParentNode, selector: string): string[] {
  return [...root.querySelectorAll(selector)].map((el) => el.getAttribute('text') ?? '');
}

/** Clicks a design-system button by its text; throws when it is not there. */
export function clickButton(root: ParentNode, text: string): void {
  const button = [...root.querySelectorAll('nldd-button')].find(
    (el) => el.getAttribute('text') === text,
  );
  if (!button) throw new Error(`geen knop met de tekst "${text}"`);
  button.dispatchEvent(new MouseEvent('click', { bubbles: true }));
}
