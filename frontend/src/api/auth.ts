import { apiGet } from './client';

export interface AuthPerson {
  id: string;
  name: string;
  email: string;
}

export interface AuthStatus {
  authenticated: boolean;
  /** False when the backend runs without an identity provider (local development). */
  oidc_configured: boolean;
  /** Null for someone the identity provider knows but this instance does not. */
  person: AuthPerson | null;
  /** Functions held in this instance, such as beheerder or planner. */
  functions: string[];
  /**
   * Kinds of relation the person has to anything in the instance:
   * assignment_manager, line_manager, team_member. A hint for the navigation;
   * the server decides per object.
   */
  relations?: string[];
  /**
   * Someone invited to sign a quote who has no person record here. Such a
   * visitor is not authenticated for the application: only the signing
   * pages are open to them.
   */
  guest?: AuthGuest | null;
  /** Whether a passkey alone can log in here; the login page then offers it. */
  passkey_login?: boolean;
  /** Whether this session began with a passkey instead of the identity provider. */
  passkey_session?: boolean;
}

export interface AuthGuest {
  name: string;
  email: string;
}

export const LOGIN_URL = '/api/auth/login';
export const LOGOUT_URL = '/api/auth/logout';

/**
 * Why a login ended without a session. The backend redirects to the frontend
 * with this value in the `login_error` query parameter.
 */
export const LOGIN_ERROR_PARAM = 'login_error';
export type LoginError = 'geen_toegang' | 'mislukt';

export function parseLoginError(value: string | null): LoginError | null {
  return value === 'geen_toegang' || value === 'mislukt' ? value : null;
}

/**
 * A path inside this application, or null. The backend validates the same
 * way; checking here too keeps a bad value out of the address bar.
 */
export function safeReturnPath(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  if (!value.startsWith('/') || value.startsWith('//') || value.includes('\\')) return null;
  if (value === '/api' || value.startsWith('/api/')) return null;
  return value;
}

/** The login URL, with the page to come back to afterwards. */
export function loginUrl(next?: string | null): string {
  const path = safeReturnPath(next);
  // The start page is where a login lands anyway.
  if (!path || path === '/') return LOGIN_URL;
  return `${LOGIN_URL}?${new URLSearchParams({ next: path }).toString()}`;
}

export function fetchAuthStatus(): Promise<AuthStatus> {
  return apiGet<AuthStatus>('/api/auth/status');
}
