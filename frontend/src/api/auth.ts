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
}

export const LOGIN_URL = '/api/auth/login';
export const LOGOUT_URL = '/api/auth/logout';

export function fetchAuthStatus(): Promise<AuthStatus> {
  return apiGet<AuthStatus>('/api/auth/status');
}
