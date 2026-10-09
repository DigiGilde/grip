import { Navigate, useLocation } from 'react-router-dom';
import { parseLoginError } from '@/api/auth';
import { useAuth } from '@/auth/context';
import { useInstance } from '@/layout/useInstance';
import { PATHS } from '@/paths';
import { StatusPage } from './StatusPage';

/** Set when the backend refused the login because this instance does not know the person. */
function loginRefused(state: unknown): boolean {
  const value = (state as { loginError?: unknown } | null)?.loginError;
  return parseLoginError(typeof value === 'string' ? value : null) === 'geen_toegang';
}

/**
 * For someone who logged in with SSO Rijk but has no person record in this
 * instance. The backend gives such a login no session, so the visitor is
 * unauthenticated here and only the redirect tells why. Logging out ends the
 * session at SSO Rijk, which is the only way forward: a different account,
 * or asking the administrator to be added.
 */
export function NoAccessPage() {
  const { state, logout } = useAuth();
  const location = useLocation();
  const instance = useInstance();
  const refused = loginRefused(location.state);

  if (state.status === 'loading') {
    return <StatusPage variant="loading" title="Grip wordt geladen" />;
  }
  if (state.status === 'authenticated') {
    return <Navigate to={PATHS.statusOverview} replace />;
  }
  if (state.status === 'guest') {
    return <Navigate to={PATHS.signing} replace />;
  }
  if (state.status === 'unauthenticated' && !refused) {
    return <Navigate to={PATHS.login} replace />;
  }

  return (
    <StatusPage
      variant="alert"
      title="Geen toegang"
      message={
        instance?.example
          ? 'Dit is een voorbeeld van grip. Je adres staat niet op de lijst van bezoekers. Vraag wie je de link gaf om je toe te voegen.'
          : 'Je bent ingelogd bij SSO Rijk, maar je hebt geen toegang tot deze omgeving. Vraag de beheerder om je toe te voegen.'
      }
      action={{ text: 'Uitloggen', onClick: logout }}
    />
  );
}
