import type { ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { StatusPage } from '@/pages/StatusPage';
import { PATHS } from '@/paths';
import { useAuth } from './context';

/**
 * Renders its children only for someone with a person record in this instance.
 * Everyone else is sent to the page that says why.
 */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { state } = useAuth();
  const location = useLocation();

  switch (state.status) {
    case 'loading':
      return <StatusPage variant="loading" title="Grip wordt geladen" />;
    case 'error':
      return (
        <StatusPage
          variant="alert"
          title="Grip is niet bereikbaar"
          message={state.message}
          action={{ text: 'Opnieuw proberen', onClick: state.retry }}
        />
      );
    case 'unauthenticated':
      return (
        <Navigate
          to={PATHS.login}
          replace
          state={{ from: `${location.pathname}${location.search}${location.hash}` }}
        />
      );
    case 'no-access':
      return <Navigate to={PATHS.noAccess} replace />;
    case 'guest':
      // An invited signer never enters the application; whatever address
      // they typed, they end up at the quotes waiting for them.
      return <Navigate to={PATHS.signing} replace />;
    case 'authenticated':
      return <>{children}</>;
  }
}

/**
 * The guard of the signing pages: a person of this instance, or an invited
 * signer with a guest session. The backend decides per quote what either
 * of them sees.
 */
export function RequireSigner({ children }: { children: ReactNode }) {
  const { state } = useAuth();
  if (state.status === 'guest') return <>{children}</>;
  return <RequireAuth>{children}</RequireAuth>;
}
