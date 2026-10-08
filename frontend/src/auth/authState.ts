import type { AuthStatus } from '@/api/auth';
import type { AuthState } from './context';

export const AUTH_STATUS_KEY = ['auth', 'status'] as const;

/** Maps the backend's answer onto the states the UI distinguishes. */
export function toAuthState(status: AuthStatus): AuthState {
  if (!status.authenticated) {
    return { status: 'unauthenticated', oidcConfigured: status.oidc_configured };
  }
  if (!status.person) return { status: 'no-access' };
  return { status: 'authenticated', person: status.person, functions: status.functions };
}
