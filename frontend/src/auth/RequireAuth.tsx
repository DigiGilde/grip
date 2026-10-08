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
      return <Navigate to={PATHS.login} replace state={{ from: location.pathname }} />;
    case 'no-access':
      return <Navigate to={PATHS.noAccess} replace />;
    case 'authenticated':
      return <>{children}</>;
  }
}
