import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, apiDelete, apiGet, apiPost, errorMessage, getCsrfToken } from './client';

function jsonResponse(body: unknown, init: ResponseInit & { contentType?: string } = {}) {
  const { contentType = 'application/json', ...rest } = init;
  return new Response(JSON.stringify(body), {
    status: 200,
    ...rest,
    headers: { 'Content-Type': contentType },
  });
}

function lastCall(fetchMock: ReturnType<typeof vi.fn>) {
  const call = fetchMock.mock.calls.at(-1);
  if (!call) throw new Error('fetch was not called');
  const [url, init] = call as [string, RequestInit];
  return { url, init, headers: init.headers as Record<string, string> };
}

describe('api client', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    document.cookie = 'grip_csrf=token-123';
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    document.cookie = 'grip_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT';
  });

  it('reads the CSRF token from the grip_csrf cookie', () => {
    expect(getCsrfToken()).toBe('token-123');
  });

  it('returns an empty token when the cookie is absent', () => {
    document.cookie = 'grip_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT';
    expect(getCsrfToken()).toBe('');
  });

  it('sends GET requests with the session cookie and without a CSRF header', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ ok: true }));

    await expect(apiGet('/api/instance')).resolves.toEqual({ ok: true });

    const { url, init, headers } = lastCall(fetchMock);
    expect(url).toBe('/api/instance');
    expect(init.method).toBe('GET');
    expect(init.credentials).toBe('same-origin');
    expect(headers['X-CSRF-Token']).toBeUndefined();
  });

  it('appends query parameters and skips empty ones', async () => {
    fetchMock.mockResolvedValue(jsonResponse([]));

    await apiGet('/api/things', { year: 2026, search: '', missing: undefined, open: true });

    expect(lastCall(fetchMock).url).toBe('/api/things?year=2026&open=true');
  });

  it('sends the CSRF header and a JSON body on POST', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ id: '1' }, { status: 201 }));

    await apiPost('/api/things', { name: 'x' });

    const { init, headers } = lastCall(fetchMock);
    expect(init.method).toBe('POST');
    expect(headers['X-CSRF-Token']).toBe('token-123');
    expect(headers['Content-Type']).toBe('application/json');
    expect(init.body).toBe('{"name":"x"}');
  });

  it('sends the CSRF header on DELETE and returns undefined for 204', async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));

    await expect(apiDelete('/api/things/1')).resolves.toBeUndefined();

    expect(lastCall(fetchMock).headers['X-CSRF-Token']).toBe('token-123');
  });

  it('turns a problem+json response into an ApiError with the problem details', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        { type: 'about:blank', title: 'Forbidden', status: 403, detail: 'Geen toegang tot deze opdracht.' },
        { status: 403, contentType: 'application/problem+json' },
      ),
    );

    const error = await apiGet('/api/things/1').catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ApiError);
    const apiError = error as ApiError;
    expect(apiError.status).toBe(403);
    expect(apiError.problem?.title).toBe('Forbidden');
    expect(apiError.message).toBe('Geen toegang tot deze opdracht.');
    expect(errorMessage(apiError)).toBe('Geen toegang tot deze opdracht.');
  });

  it('reads a plain JSON detail as a problem', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: 'Niet gevonden.' }, { status: 404 }));

    const error = (await apiGet('/api/things/1').catch((e: unknown) => e)) as ApiError;

    expect(error.problem?.detail).toBe('Niet gevonden.');
  });

  it('keeps a non-JSON error body and falls back to a generic message', async () => {
    fetchMock.mockResolvedValue(
      new Response('<html>Bad Gateway</html>', {
        status: 502,
        statusText: 'Bad Gateway',
        headers: { 'Content-Type': 'text/html' },
      }),
    );

    const error = (await apiGet('/api/things').catch((e: unknown) => e)) as ApiError;

    expect(error.status).toBe(502);
    expect(error.problem).toBeNull();
    expect(error.body).toBe('<html>Bad Gateway</html>');
    expect(errorMessage(error)).toBe('Er ging iets mis. Probeer het later opnieuw.');
  });

  it('gives status-specific messages when the body says nothing', () => {
    expect(errorMessage(new ApiError(401, 'Unauthorized', '', null))).toBe('Je bent niet ingelogd.');
    expect(errorMessage(new ApiError(403, 'Forbidden', '', null))).toBe(
      'Je hebt geen toegang tot deze gegevens.',
    );
  });

  it('describes a network failure as an unreachable server', () => {
    expect(errorMessage(new TypeError('Failed to fetch'))).toMatch(/niet bereikbaar/);
  });
});
