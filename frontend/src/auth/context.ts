import { createContext, useContext } from 'react';
import type { AuthGuest, AuthPerson } from '@/api/auth';

export type AuthState =
  | { status: 'loading' }
  | { status: 'error'; message: string; retry: () => void }
  | { status: 'unauthenticated'; oidcConfigured: boolean }
  /** Known to the identity provider, but without a person record in this instance. */
  | { status: 'no-access' }
  /** Invited to sign a quote, without a person record: the signing pages only. */
  | { status: 'guest'; guest: AuthGuest }
  | { status: 'authenticated'; person: AuthPerson; functions: string[] };

export interface AuthContextValue {
  state: AuthState;
  /** Starts the login; `next` is the page to come back to afterwards. */
  login: (next?: string) => void;
  logout: () => void;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error('useAuth must be used inside an AuthProvider');
  return value;
}
