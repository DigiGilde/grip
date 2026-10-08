import { Navigate, Route, Routes, useSearchParams } from 'react-router-dom';
import { LOGIN_ERROR_PARAM, parseLoginError } from '@/api/auth';
import { RequireAuth, RequireSigner } from '@/auth/RequireAuth';
import { AppShell } from '@/layout/AppShell';
import { AdminPage } from '@/pages/AdminPage';
import { LoginPage } from '@/pages/LoginPage';
import { NoAccessPage } from '@/pages/NoAccessPage';
import { NotFoundPage } from '@/pages/NotFoundPage';
import { PATHS } from '@/paths';
import { AllocationsPage } from '@/features/allocations/AllocationsPage';
import { AssignmentLayout } from '@/features/assignments/AssignmentLayout';
import { ASSIGNMENT_TAB_SEGMENTS } from '@/features/assignments/paths';
import { BudgetTab } from '@/features/assignments/tabs/BudgetTab';
import { FinanceTab } from '@/features/assignments/tabs/FinanceTab';
import { OverviewTab } from '@/features/assignments/tabs/OverviewTab';
import { StaffingTab } from '@/features/assignments/tabs/StaffingTab';
import { AssignmentsPage } from '@/features/assignments/AssignmentsPage';
import { ClientAssignmentPage } from '@/features/client/ClientAssignmentPage';
import { ClientPage } from '@/features/client/ClientPage';
import { ReceivedQuotePage } from '@/features/client/ReceivedQuotePage';
import { RequestQuotePage } from '@/features/client/RequestQuotePage';
import { BillingPage } from '@/features/billing/BillingPage';
import { DeliveryPage } from '@/features/billing/DeliveryPage';
import { CostItemPage } from '@/features/costs/CostItemPage';
import { NotificationsPage } from '@/features/notifications/NotificationsPage';
import { SecurityPage } from '@/features/passkeys/SecurityPage';
import { CostsPage } from '@/features/costs/CostsPage';
import { MonthClosePage } from '@/features/month-close/MonthClosePage';
import { OverviewPage } from '@/features/overview/OverviewPage';
import { QuotePage } from '@/features/quotes/QuotePage';
import { ApprovalListPage } from '@/features/quotes/ApprovalListPage';
import { ApprovalPage } from '@/features/quotes/ApprovalPage';
import { QuoteDraftPage } from '@/features/quotes/QuoteDraftPage';
import { QuoteSettingsPage } from '@/features/quotes/QuoteSettingsPage';
import { SenderPage } from '@/features/quote-letter/SenderPage';
import { VerifyProofPage } from '@/features/quotes/VerifyProofPage';
import { SigningLayout } from '@/features/signing/SigningLayout';
import { SigningListPage } from '@/features/signing/SigningListPage';
import { SigningPage } from '@/features/signing/SigningPage';
import { OrganisationsAdminPage } from '@/features/organisations/OrganisationsAdminPage';
import { RolesAdminPage } from '@/features/roles/RolesAdminPage';
import { PeersPage } from '@/features/peers/PeersPage';
import { RatesPage } from '@/features/rates/RatesPage';
import { ActivityPage, AssignmentHistoryTab, VacancyHistoryTab } from '@/features/history/History';
import { UpdatesPage } from '@/features/history/UpdateFeed';
import { AssignmentTasksTab, VacancyTasksTab } from '@/features/tasks/CaseTasks';
import { TasksPage } from '@/features/tasks/TasksPage';
import { AssignmentReportPage } from '@/features/reports/AssignmentReportPage';
import { ReportsPage } from '@/features/reports/ReportsPage';
import { ReportTopicPage } from '@/features/reports/ReportTopicPage';
import { PersonPage } from '@/features/team/PersonPage';
import { TeamPage } from '@/features/team/TeamPage';
import { VacancySetupPage } from '@/features/form-templates/VacancySetupPage';
import { FormTemplatePage } from '@/features/form-templates/FormTemplatePage';
import { FunctionFrameworkPage } from '@/features/function-framework/FunctionFrameworkPage';
import { WiesProposalsPage } from '@/features/wies/WiesProposalsPage';
import { OpenRolesPage } from '@/features/vacancies/OpenRolesPage';
import { StandardTextsPage } from '@/features/vacancies/StandardTextsPage';
import { VacanciesPage } from '@/features/vacancies/VacanciesPage';
import { VACANCY_TAB_SEGMENTS } from '@/features/vacancies/paths';
import {
  DecisionsTab,
  FulfilmentTab,
  ProcedureTab,
  RequestTab,
  TextTab,
} from '@/features/vacancies/tabs/VacancyTabs';
import { VacancyLayout } from '@/features/vacancies/VacancyLayout';
import type { ReactElement } from 'react';

/**
 * The screen behind each page of the first level. A page has its address
 * whether or not the navigation names it: the bar decides what it offers,
 * never what exists.
 */
const SCREENS: Record<string, ReactElement> = {
  [PATHS.statusOverview]: <OverviewPage />,
  [PATHS.tasks]: <TasksPage />,
  [PATHS.assignments]: <AssignmentsPage />,
  [PATHS.allocations]: <AllocationsPage />,
  [PATHS.costs]: <CostsPage />,
  [PATHS.billing]: <BillingPage />,
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
        {Object.entries(SCREENS).map(([path, element]) => (
          <Route key={path} path={path} element={element} />
        ))}
        {/* One assignment: a shared header and tabs around one page per concern. */}
        <Route path={PATHS.assignmentDetail} element={<AssignmentLayout />}>
          <Route index element={<OverviewTab />} />
          <Route path={ASSIGNMENT_TAB_SEGMENTS.tasks} element={<AssignmentTasksTab />} />
          <Route path={ASSIGNMENT_TAB_SEGMENTS.finance} element={<FinanceTab />} />
          <Route path={ASSIGNMENT_TAB_SEGMENTS.staffing} element={<StaffingTab />} />
          <Route path={ASSIGNMENT_TAB_SEGMENTS.budget} element={<BudgetTab />} />
          <Route path={ASSIGNMENT_TAB_SEGMENTS.quote} element={<QuotePage />} />
          <Route path={ASSIGNMENT_TAB_SEGMENTS.monthClose} element={<MonthClosePage />} />
          <Route path={ASSIGNMENT_TAB_SEGMENTS.history} element={<AssignmentHistoryTab />} />
        </Route>
        <Route path={PATHS.activity} element={<ActivityPage />} />
        <Route path={PATHS.updates} element={<UpdatesPage />} />
        <Route path={PATHS.vacancyOpenRoles} element={<OpenRolesPage />} />
        <Route path={PATHS.vacancySetup} element={<VacancySetupPage />} />
        <Route path={PATHS.vacancyStandardTexts} element={<StandardTextsPage />} />
        <Route path={PATHS.formTemplate} element={<FormTemplatePage />} />
        <Route path={PATHS.functionFramework} element={<FunctionFrameworkPage />} />
        {/* One vacancy: a shared header with the steps, and a tab per concern. */}
        <Route path={PATHS.vacancyDetail} element={<VacancyLayout />}>
          <Route index element={<RequestTab />} />
          <Route path={VACANCY_TAB_SEGMENTS.tasks} element={<VacancyTasksTab />} />
          <Route path={VACANCY_TAB_SEGMENTS.decisions} element={<DecisionsTab />} />
          <Route path={VACANCY_TAB_SEGMENTS.text} element={<TextTab />} />
          <Route path={VACANCY_TAB_SEGMENTS.procedure} element={<ProcedureTab />} />
          <Route path={VACANCY_TAB_SEGMENTS.fulfilment} element={<FulfilmentTab />} />
          <Route path={VACANCY_TAB_SEGMENTS.history} element={<VacancyHistoryTab />} />
        </Route>
        <Route path={PATHS.clientRequest} element={<RequestQuotePage />} />
        <Route path={PATHS.clientAssignment} element={<ClientAssignmentPage />} />
        <Route path={PATHS.receivedQuote} element={<ReceivedQuotePage />} />
        <Route path={PATHS.assignmentQuoteDraft} element={<QuoteDraftPage />} />
        <Route path={PATHS.quoteApprovals} element={<ApprovalListPage />} />
        <Route path={PATHS.quoteApproval} element={<ApprovalPage />} />
        <Route path={PATHS.quoteSettings} element={<QuoteSettingsPage />} />
        <Route path={PATHS.quoteSender} element={<SenderPage />} />
        <Route path={PATHS.peers} element={<PeersPage />} />
        <Route path={PATHS.organisations} element={<OrganisationsAdminPage />} />
        <Route path={PATHS.roles} element={<RolesAdminPage />} />
        <Route path={PATHS.rates} element={<RatesPage />} />
        <Route path={PATHS.teamPerson} element={<PersonPage />} />
        <Route path={PATHS.costItem} element={<CostItemPage />} />
        <Route path={PATHS.billingDelivery} element={<DeliveryPage />} />
        <Route path={PATHS.security} element={<SecurityPage />} />
        <Route path={PATHS.notifications} element={<NotificationsPage />} />
        <Route path={PATHS.ratesLegacy} element={<Navigate to={PATHS.rates} replace />} />
        <Route path={PATHS.wiesProposals} element={<WiesProposalsPage />} />
        <Route path={PATHS.reportAssignment} element={<AssignmentReportPage />} />
        <Route path={PATHS.reportTopic} element={<ReportTopicPage />} />
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
        <Route path={PATHS.verifyProof} element={<VerifyProofPage />} />
      </Route>
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}
