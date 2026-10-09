/**
 * Typed fetch wrapper for the grip API.
 *
 * Requests go to the same origin: the Vite dev server and the nginx container
 * both proxy /api to the backend, so the session and CSRF cookies are
 * first-party everywhere.
 */

const CSRF_COOKIE = 'grip_csrf';
const CSRF_HEADER = 'X-CSRF-Token';

/** The body of an error response per RFC 9457 (application/problem+json). */
export interface ProblemDetails {
  type?: string;
  title?: string;
  status?: number;
  detail?: string;
  instance?: string;
  [extension: string]: unknown;
}

export class ApiError extends Error {
  readonly status: number;
  readonly problem: ProblemDetails | null;
  readonly body: unknown;

  constructor(status: number, statusText: string, body: unknown, problem: ProblemDetails | null) {
    super(problem?.detail ?? problem?.title ?? `API-fout ${status}: ${statusText}`);
    this.name = 'ApiError';
    this.status = status;
    this.body = body;
    this.problem = problem;
  }
}

/** Double-submit CSRF token: the value of the cookie the backend set. */
export function getCsrfToken(): string {
  const match = document.cookie.match(new RegExp(`(?:^|;\\s*)${CSRF_COOKIE}=([^;]*)`));
  return match?.[1] ? decodeURIComponent(match[1]) : '';
}

/** A message for the user, in Dutch, for anything a request can throw. */
export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.problem?.detail) return error.problem.detail;
    if (error.problem?.title) return error.problem.title;
    if (error.status === 401) return 'Je bent niet ingelogd.';
    if (error.status === 403) return 'Je hebt geen toegang tot deze gegevens.';
    if (error.status === 404) return 'Dit is niet gevonden.';
    return 'Er ging iets mis. Probeer het later opnieuw.';
  }
  return 'De server is niet bereikbaar. Controleer je verbinding en probeer het opnieuw.';
}

/** Why a request for data gave nothing to show. */
export type LoadFailure = 'no-access' | 'not-found' | 'unreachable' | 'failed';

/**
 * What kind of failure a request for data ended in. A screen shows one of
 * four states for it and nothing else; see `LoadError` in `@/ui/layout`.
 */
export function loadFailure(error: unknown): LoadFailure {
  if (!(error instanceof ApiError)) return 'unreachable';
  if (error.status === 401 || error.status === 403) return 'no-access';
  if (error.status === 404) return 'not-found';
  if (error.status === 502 || error.status === 503 || error.status === 504) return 'unreachable';
  return 'failed';
}

/**
 * Whether a failed request for data is worth asking again. An answer of the
 * server about this reader (no access, not found, refused) does not change by
 * asking again; only a failure to get an answer does. Without this a screen
 * keeps saying "Bezig met laden" for seconds after the server said no.
 */
export function retryLoad(failureCount: number, error: unknown): boolean {
  if (error instanceof ApiError && error.status < 500) return false;
  return failureCount < 1;
}

type QueryParams = Record<string, string | number | boolean | undefined | null>;

function buildUrl(path: string, params?: QueryParams): string {
  if (!params) return path;
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') search.append(key, String(value));
  }
  const query = search.toString();
  return query ? `${path}?${query}` : path;
}

function isProblem(contentType: string, body: unknown): body is ProblemDetails {
  if (typeof body !== 'object' || body === null || Array.isArray(body)) return false;
  if (contentType.includes('application/problem+json')) return true;
  // FastAPI's default error shape is {"detail": "..."} as plain JSON; treat a
  // string detail as a problem so callers have one place to look.
  const candidate = body as Record<string, unknown>;
  return typeof candidate.detail === 'string' || typeof candidate.title === 'string';
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (response.ok) {
    if (response.status === 204) return undefined as T;
    return (await response.json()) as T;
  }

  const contentType = response.headers.get('Content-Type') ?? '';
  const text = await response.text();
  let body: unknown = text;
  if (contentType.includes('json')) {
    try {
      body = JSON.parse(text);
    } catch {
      body = text;
    }
  }
  throw new ApiError(
    response.status,
    response.statusText,
    body,
    isProblem(contentType, body) ? body : null,
  );
}

const MUTATING = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

/** Extra request headers, such as the version a save started from. */
export type RequestHeaders = Record<string, string>;

async function request<T>(
  method: string,
  url: string,
  data?: unknown,
  extra?: RequestHeaders,
): Promise<T> {
  const headers: Record<string, string> = {
    Accept: 'application/json, application/problem+json',
    ...extra,
  };
  if (data !== undefined) headers['Content-Type'] = 'application/json';
  if (MUTATING.has(method)) headers[CSRF_HEADER] = getCsrfToken();

  const response = await fetch(url, {
    method,
    headers,
    credentials: 'same-origin',
    body: data !== undefined ? JSON.stringify(data) : undefined,
  });
  return handleResponse<T>(response);
}

export function apiGet<T>(path: string, params?: QueryParams): Promise<T> {
  return request<T>('GET', buildUrl(path, params));
}

export function apiPost<T>(path: string, data?: unknown, headers?: RequestHeaders): Promise<T> {
  return request<T>('POST', path, data, headers);
}

export function apiPut<T>(path: string, data?: unknown, headers?: RequestHeaders): Promise<T> {
  return request<T>('PUT', path, data, headers);
}

export function apiPatch<T>(path: string, data?: unknown, headers?: RequestHeaders): Promise<T> {
  return request<T>('PATCH', path, data, headers);
}

export function apiDelete<T = void>(path: string, headers?: RequestHeaders): Promise<T> {
  return request<T>('DELETE', path, undefined, headers);
}
