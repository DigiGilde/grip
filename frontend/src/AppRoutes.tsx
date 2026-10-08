import { Route, Routes } from 'react-router-dom';
import { RequireAuth } from '@/auth/RequireAuth';
import { AppShell } from '@/layout/AppShell';
import { LoginPage } from '@/pages/LoginPage';
import { NoAccessPage } from '@/pages/NoAccessPage';
import { NotFoundPage } from '@/pages/NotFoundPage';
import { PlaceholderPage } from '@/pages/PlaceholderPage';
import { PATHS } from '@/paths';
import { APP_ROUTES } from '@/routes';

export function AppRoutes() {
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
