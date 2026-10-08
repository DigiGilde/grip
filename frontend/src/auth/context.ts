import { createContext, useContext } from 'react';
import type { AuthPerson } from '@/api/auth';

export type AuthState =
  | { status: 'loading' }
  | { status: 'error'; message: string; retry: () => void }
  | { status: 'unauthenticated'; oidcConfigured: boolean }
  /** Known to the identity provider, but without a person record in this instance. */
  | { status: 'no-access' }
  | { status: 'authenticated'; person: AuthPerson; functions: string[] };

export interface AuthContextValue {
  state: AuthState;
  login: () => void;
  logout: () => void;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error('useAuth must be used inside an AuthProvider');
  return value;
}
