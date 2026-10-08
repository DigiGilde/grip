import { Navigate, Route, Routes, useSearchParams } from 'react-router-dom';
import { LOGIN_ERROR_PARAM, parseLoginError } from '@/api/auth';
import { RequireAuth, RequireSigner } from '@/auth/RequireAuth';
import { AppShell } from '@/layout/AppShell';
import { AdminPage } from '@/pages/AdminPage';
import { LoginPage } from '@/pages/LoginPage';
import { NoAccessPage } from '@/pages/NoAccessPage';
import { NotFoundPage } from '@/pages/NotFoundPage';
import { PlaceholderPage } from '@/pages/PlaceholderPage';
import { PATHS } from '@/paths';
import { APP_ROUTES } from '@/routes';
import { AllocationsPage } from '@/features/allocations/AllocationsPage';
import { AssignmentDetailPage } from '@/features/assignments/AssignmentDetailPage';
import { AssignmentsPage } from '@/features/assignments/AssignmentsPage';
import { ClientAssignmentPage } from '@/features/client/ClientAssignmentPage';
import { ClientPage } from '@/features/client/ClientPage';
import { ReceivedQuotePage } from '@/features/client/ReceivedQuotePage';
import { RequestQuotePage } from '@/features/client/RequestQuotePage';
import { CostsPage } from '@/features/costs/CostsPage';
import { MonthClosePage } from '@/features/month-close/MonthClosePage';
import { OverviewPage } from '@/features/overview/OverviewPage';
import { QuotePage } from '@/features/quotes/QuotePage';
import { SigningLayout } from '@/features/signing/SigningLayout';
import { SigningListPage } from '@/features/signing/SigningListPage';
import { SigningPage } from '@/features/signing/SigningPage';
import { PeersPage } from '@/features/peers/PeersPage';
import { RatesPage } from '@/features/rates/RatesPage';
import { AssignmentReportPage } from '@/features/reports/AssignmentReportPage';
import { ReportsPage } from '@/features/reports/ReportsPage';
import { TeamPage } from '@/features/team/TeamPage';
import { VacancySetupPage } from '@/features/form-templates/VacancySetupPage';
import { WiesProposalsPage } from '@/features/wies/WiesProposalsPage';
import { OpenRolesPage } from '@/features/vacancies/OpenRolesPage';
import { VacanciesPage } from '@/features/vacancies/VacanciesPage';
import { VacancyDetailPage } from '@/features/vacancies/VacancyDetailPage';
import type { ReactElement } from 'react';

/**
 * The screen behind each path of the navigation. A path without an entry
 * shows the placeholder. Add your screen here; leave the others alone.
 */
const SCREENS: Record<string, ReactElement> = {
  [PATHS.statusOverview]: <OverviewPage />,
  [PATHS.assignments]: <AssignmentsPage />,
  [PATHS.allocations]: <AllocationsPage />,
  [PATHS.costs]: <CostsPage />,
  [PATHS.rates]: <RatesPage />,
  [PATHS.team]: <TeamPage />,
  [PATHS.vacancies]: <VacanciesPage />,
  [PATHS.reports]: <ReportsPage />,
  [PATHS.client]: <ClientPage />,
  [PATHS.admin]: <AdminPage />,
};

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
            element={SCREENS[route.path] ?? <PlaceholderPage title={route.title} />}
          />
        ))}
        <Route path={PATHS.assignmentDetail} element={<AssignmentDetailPage />} />
        <Route path={PATHS.vacancyOpenRoles} element={<OpenRolesPage />} />
        <Route path={PATHS.vacancySetup} element={<VacancySetupPage />} />
        <Route path={PATHS.vacancyDetail} element={<VacancyDetailPage />} />
        <Route path={PATHS.clientRequest} element={<RequestQuotePage />} />
        <Route path={PATHS.clientAssignment} element={<ClientAssignmentPage />} />
        <Route path={PATHS.receivedQuote} element={<ReceivedQuotePage />} />
        <Route path={PATHS.peers} element={<PeersPage />} />
        <Route path={PATHS.wiesProposals} element={<WiesProposalsPage />} />
        <Route path={PATHS.assignmentQuote} element={<QuotePage />} />
        <Route path={PATHS.assignmentMonthClose} element={<MonthClosePage />} />
        <Route path={PATHS.reportAssignment} element={<AssignmentReportPage />} />
      </Route>
      <Route
        element={
          <RequireSigner>
            <SigningLayout />
          </RequireSigner>
        }
      >
        <Route path={PATHS.signing} element={<SigningListPage />} />
        <Route path={PATHS.signingQuote} element={<SigningPage />} />
      </Route>
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}
