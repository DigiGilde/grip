import { Navigate, Route, Routes, useSearchParams } from 'react-router-dom';
import { LOGIN_ERROR_PARAM, parseLoginError } from '@/api/auth';
import { RequireAuth } from '@/auth/RequireAuth';
import { AppShell } from '@/layout/AppShell';
import { LoginPage } from '@/pages/LoginPage';
import { NoAccessPage } from '@/pages/NoAccessPage';
import { NotFoundPage } from '@/pages/NotFoundPage';
import { PlaceholderPage } from '@/pages/PlaceholderPage';
import { PATHS } from '@/paths';
import { APP_ROUTES } from '@/routes';

export function AppRoutes() {
  // A login that ended without a session comes back to the start page with
  // the reason in the query string. Move to the page that explains it; the
  // navigation drops the parameter, so this runs once.
  const [searchParams] = useSearchParams();
  const loginError = parseLoginError(searchParams.get(LOGIN_ERROR_PARAM));
  if (loginError) {
    return (
      <Navigate
        to={loginError === 'geen_toegang' ? PATHS.noAccess : PATHS.login}
        replace
        state={{ loginError }}
      />
    );
  }

  return (
    <Routes>
      <Route path={PATHS.login} element={<LoginPage />} />
      <Route path={PATHS.noAccess} element={<NoAccessPage />} />
      <Route
        element={
          <RequireAuth>
            <AppShell />
          </RequireAuth>
        }
      >
        {APP_ROUTES.map((route) => (
          <Route
            key={route.path}
            path={route.path}
            element={<PlaceholderPage title={route.title} />}
          />
        ))}
      </Route>
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}
