import { Navigate } from 'react-router-dom';
import { useAuth } from '@/auth/context';
import { PATHS } from '@/paths';
import { StatusPage } from './StatusPage';

/**
 * For someone who logged in with SSO Rijk but has no person record in this
 * instance. Logging out is the only way forward: a different account, or
 * asking the administrator to be added.
 */
export function NoAccessPage() {
  const { state, logout } = useAuth();

  if (state.status === 'loading') {
    return <StatusPage variant="loading" title="Grip wordt geladen" />;
  }
  if (state.status === 'authenticated') {
    return <Navigate to={PATHS.statusOverview} replace />;
  }
  if (state.status === 'unauthenticated') {
    return <Navigate to={PATHS.login} replace />;
  }

  return (
    <StatusPage
      variant="alert"
      title="Geen toegang"
      message="Je bent ingelogd, maar je hebt geen toegang tot deze omgeving. Vraag de beheerder om je toe te voegen."
      action={{ text: 'Uitloggen', onClick: logout }}
    />
  );
}
