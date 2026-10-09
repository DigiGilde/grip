import { Navigate, Route, Routes, useLocation, useSearchParams } from 'react-router-dom';
import { LOGIN_ERROR_PARAM, parseLoginError } from '@/api/auth';
import { RequireAuth, RequireSigner } from '@/auth/RequireAuth';
import { AppShell } from '@/layout/AppShell';
import { PageBoundary } from '@/PageBoundary';
import { AdminOnly } from '@/pages/AdminOnly';
import { LoginPage } from '@/pages/LoginPage';
import { NoAccessPage } from '@/pages/NoAccessPage';
import { NotFoundPage } from '@/pages/NotFoundPage';
import { PATHS } from '@/paths';
import { ASSIGNMENT_TAB_SEGMENTS } from '@/features/assignments/paths';
import { OverviewPage } from '@/features/overview/OverviewPage';
import { TasksPage } from '@/features/tasks/TasksPage';
import { VACANCY_TAB_SEGMENTS } from '@/features/vacancies/paths';
import { page, preloadFor } from '@/pageChunks';
import type { ReactElement } from 'react';

// The shell, the start page and the tasks come with the first load. Every
// page below is a file of its own, fetched on the way to it (see
// `pageChunks`): the patterns say for which addresses.
const ASSIGNMENT = `${PATHS.assignmentDetail}/*`;
const VACANCY = `${PATHS.vacancyDetail}/*`;
const assignmentTab = (segment: string) => `${PATHS.assignmentDetail}/${segment}`;
const vacancyTab = (segment: string) => `${PATHS.vacancyDetail}/${segment}`;

const AdminPage = page(() => import('@/pages/AdminPage'), 'AdminPage', PATHS.admin);
const AllocationsPage = page(
  () => import('@/features/allocations/AllocationsPage'),
  'AllocationsPage',
  PATHS.allocations,
);
const AssignmentsPage = page(
  () => import('@/features/assignments/AssignmentsPage'),
  'AssignmentsPage',
  PATHS.assignments,
);
const AssignmentLayout = page(
  () => import('@/features/assignments/AssignmentLayout'),
  'AssignmentLayout',
  ASSIGNMENT,
);
const AssignmentTab = page(
  () => import('@/features/assignments/TabGuard'),
  'AssignmentTab',
  ASSIGNMENT,
);
const OverviewTab = page(
  () => import('@/features/assignments/tabs/OverviewTab'),
  'OverviewTab',
  PATHS.assignmentDetail,
);
const FinanceTab = page(
  () => import('@/features/assignments/tabs/FinanceTab'),
  'FinanceTab',
  assignmentTab(ASSIGNMENT_TAB_SEGMENTS.finance),
);
const StaffingTab = page(
  () => import('@/features/assignments/tabs/StaffingTab'),
  'StaffingTab',
  assignmentTab(ASSIGNMENT_TAB_SEGMENTS.staffing),
);
const BudgetTab = page(
  () => import('@/features/assignments/tabs/BudgetTab'),
  'BudgetTab',
  assignmentTab(ASSIGNMENT_TAB_SEGMENTS.budget),
);
const QuotePage = page(
  () => import('@/features/quotes/QuotePage'),
  'QuotePage',
  assignmentTab(ASSIGNMENT_TAB_SEGMENTS.quote),
);
const MonthClosePage = page(
  () => import('@/features/month-close/MonthClosePage'),
  'MonthClosePage',
  assignmentTab(ASSIGNMENT_TAB_SEGMENTS.monthClose),
);
const caseTasks = () => import('@/features/tasks/CaseTasks');
const AssignmentTasksTab = page(
  caseTasks,
  'AssignmentTasksTab',
  assignmentTab(ASSIGNMENT_TAB_SEGMENTS.tasks),
);
const VacancyTasksTab = page(caseTasks, 'VacancyTasksTab', vacancyTab(VACANCY_TAB_SEGMENTS.tasks));
const history = () => import('@/features/history/History');
const ActivityPage = page(history, 'ActivityPage', PATHS.activity);
const AssignmentHistoryTab = page(
  history,
  'AssignmentHistoryTab',
  assignmentTab(ASSIGNMENT_TAB_SEGMENTS.history),
);
const VacancyHistoryTab = page(
  history,
  'VacancyHistoryTab',
  vacancyTab(VACANCY_TAB_SEGMENTS.history),
);
const UpdatesPage = page(
  () => import('@/features/history/UpdateFeed'),
  'UpdatesPage',
  PATHS.updates,
);
const ClientPage = page(() => import('@/features/client/ClientPage'), 'ClientPage', PATHS.client);
const ClientAssignmentPage = page(
  () => import('@/features/client/ClientAssignmentPage'),
  'ClientAssignmentPage',
  PATHS.clientAssignment,
);
const ReceivedQuotePage = page(
  () => import('@/features/client/ReceivedQuotePage'),
  'ReceivedQuotePage',
  PATHS.receivedQuote,
);
const RequestQuotePage = page(
  () => import('@/features/client/RequestQuotePage'),
  'RequestQuotePage',
  PATHS.clientRequest,
);
const BillingPage = page(
  () => import('@/features/billing/BillingPage'),
  'BillingPage',
  PATHS.billing,
);
const DeliveryPage = page(
  () => import('@/features/billing/DeliveryPage'),
  'DeliveryPage',
  PATHS.billingDelivery,
);
const CostsPage = page(() => import('@/features/costs/CostsPage'), 'CostsPage', PATHS.costs);
const CostItemPage = page(
  () => import('@/features/costs/CostItemPage'),
  'CostItemPage',
  PATHS.costItem,
);
const NotificationsPage = page(
  () => import('@/features/notifications/NotificationsPage'),
  'NotificationsPage',
  PATHS.notifications,
);
const SecurityPage = page(
  () => import('@/features/passkeys/SecurityPage'),
  'SecurityPage',
  PATHS.security,
);
const ApprovalListPage = page(
  () => import('@/features/quotes/ApprovalListPage'),
  'ApprovalListPage',
  PATHS.quoteApprovals,
);
const ApprovalPage = page(
  () => import('@/features/quotes/ApprovalPage'),
  'ApprovalPage',
  PATHS.quoteApproval,
);
const QuoteDraftPage = page(
  () => import('@/features/quotes/QuoteDraftPage'),
  'QuoteDraftPage',
  PATHS.assignmentQuoteDraft,
);
const QuoteSettingsPage = page(
  () => import('@/features/quotes/QuoteSettingsPage'),
  'QuoteSettingsPage',
  PATHS.quoteSettings,
);
const SenderPage = page(
  () => import('@/features/quote-letter/SenderPage'),
  'SenderPage',
  PATHS.quoteSender,
);
const VerifyProofPage = page(
  () => import('@/features/quotes/VerifyProofPage'),
  'VerifyProofPage',
  PATHS.verifyProof,
);
const SIGNING = `${PATHS.signing}/*`;
const SigningLayout = page(
  () => import('@/features/signing/SigningLayout'),
  'SigningLayout',
  SIGNING,
  PATHS.verifyProof,
);
const SigningListPage = page(
  () => import('@/features/signing/SigningListPage'),
  'SigningListPage',
  PATHS.signing,
);
const SigningPage = page(
  () => import('@/features/signing/SigningPage'),
  'SigningPage',
  PATHS.signingQuote,
);
const OrganisationsAdminPage = page(
  () => import('@/features/organisations/OrganisationsAdminPage'),
  'OrganisationsAdminPage',
  PATHS.organisations,
);
const RolesAdminPage = page(
  () => import('@/features/roles/RolesAdminPage'),
  'RolesAdminPage',
  PATHS.roles,
);
const PeersPage = page(() => import('@/features/peers/PeersPage'), 'PeersPage', PATHS.peers);
const RatesPage = page(() => import('@/features/rates/RatesPage'), 'RatesPage', PATHS.rates);
const AssignmentReportPage = page(
  () => import('@/features/reports/AssignmentReportPage'),
  'AssignmentReportPage',
  PATHS.reportAssignment,
);
const ReportsPage = page(
  () => import('@/features/reports/ReportsPage'),
  'ReportsPage',
  PATHS.reports,
);
const ReportTopicPage = page(
  () => import('@/features/reports/ReportTopicPage'),
  'ReportTopicPage',
  PATHS.reportTopic,
);
const PersonPage = page(() => import('@/features/team/PersonPage'), 'PersonPage', PATHS.teamPerson);
const TeamPage = page(() => import('@/features/team/TeamPage'), 'TeamPage', PATHS.team);
const VacancySetupPage = page(
  () => import('@/features/form-templates/VacancySetupPage'),
  'VacancySetupPage',
  PATHS.vacancySetup,
);
const LanguageModelPage = page(
  () => import('@/features/language-model/LanguageModelPage'),
  'LanguageModelPage',
  PATHS.languageModel,
);
const FormTemplatePage = page(
  () => import('@/features/form-templates/FormTemplatePage'),
  'FormTemplatePage',
  PATHS.formTemplate,
);
const FunctionFrameworkPage = page(
  () => import('@/features/function-framework/FunctionFrameworkPage'),
  'FunctionFrameworkPage',
  PATHS.functionFramework,
);
const WiesProposalsPage = page(
  () => import('@/features/wies/WiesProposalsPage'),
  'WiesProposalsPage',
  PATHS.wiesProposals,
);
const OpenRolesPage = page(
  () => import('@/features/vacancies/OpenRolesPage'),
  'OpenRolesPage',
  PATHS.vacancyOpenRoles,
);
const StandardTextsPage = page(
  () => import('@/features/vacancies/StandardTextsPage'),
  'StandardTextsPage',
  PATHS.vacancyStandardTexts,
);
const VacanciesPage = page(
  () => import('@/features/vacancies/VacanciesPage'),
  'VacanciesPage',
  PATHS.vacancies,
);
const vacancyTabs = () => import('@/features/vacancies/tabs/VacancyTabs');
const RequestTab = page(vacancyTabs, 'RequestTab', VACANCY);
const DecisionsTab = page(vacancyTabs, 'DecisionsTab', VACANCY);
const TextTab = page(vacancyTabs, 'TextTab', VACANCY);
const ProcedureTab = page(vacancyTabs, 'ProcedureTab', VACANCY);
const FulfilmentTab = page(vacancyTabs, 'FulfilmentTab', VACANCY);
const VacancyTab = page(() => import('@/features/vacancies/TabGuard'), 'VacancyTab', VACANCY);
const VacancyLayout = page(
  () => import('@/features/vacancies/VacancyLayout'),
  'VacancyLayout',
  VACANCY,
);
const VacancyTextPage = page(
  () => import('@/features/vacancies/VacancyTextPage'),
  'VacancyTextPage',
  PATHS.vacancyTextWrite,
);

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
  const { pathname } = useLocation();
  // A layout and the page inside it are fetched side by side.
  preloadFor(pathname);
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
    <PageBoundary resetKey={pathname} fallback={null}>
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
            <Route
              path={ASSIGNMENT_TAB_SEGMENTS.finance}
              element={
                <AssignmentTab tab="finance">
                  <FinanceTab />
                </AssignmentTab>
              }
            />
            <Route
              path={ASSIGNMENT_TAB_SEGMENTS.staffing}
              element={
                <AssignmentTab tab="staffing">
                  <StaffingTab />
                </AssignmentTab>
              }
            />
            <Route
              path={ASSIGNMENT_TAB_SEGMENTS.budget}
              element={
                <AssignmentTab tab="budget">
                  <BudgetTab />
                </AssignmentTab>
              }
            />
            <Route
              path={ASSIGNMENT_TAB_SEGMENTS.quote}
              element={
                <AssignmentTab tab="quote">
                  <QuotePage />
                </AssignmentTab>
              }
            />
            <Route
              path={ASSIGNMENT_TAB_SEGMENTS.monthClose}
              element={
                <AssignmentTab tab="monthClose">
                  <MonthClosePage />
                </AssignmentTab>
              }
            />
            <Route path={ASSIGNMENT_TAB_SEGMENTS.history} element={<AssignmentHistoryTab />} />
          </Route>
          <Route path={PATHS.activity} element={<ActivityPage />} />
          <Route path={PATHS.updates} element={<UpdatesPage />} />
          <Route path={PATHS.vacancyOpenRoles} element={<OpenRolesPage />} />
          <Route path={PATHS.vacancySetup} element={<VacancySetupPage />} />
          <Route path={PATHS.languageModel} element={<LanguageModelPage />} />
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
            <Route
              path={VACANCY_TAB_SEGMENTS.fulfilment}
              element={
                <VacancyTab tab="fulfilment">
                  <FulfilmentTab />
                </VacancyTab>
              }
            />
            <Route path={VACANCY_TAB_SEGMENTS.history} element={<VacancyHistoryTab />} />
          </Route>
          {/* Writing the vacancy text is a page of its own, outside the tabs. */}
          <Route path={PATHS.vacancyTextWrite} element={<VacancyTextPage />} />
          <Route path={PATHS.clientRequest} element={<RequestQuotePage />} />
          <Route path={PATHS.clientAssignment} element={<ClientAssignmentPage />} />
          <Route path={PATHS.receivedQuote} element={<ReceivedQuotePage />} />
          <Route path={PATHS.assignmentQuoteDraft} element={<QuoteDraftPage />} />
          <Route path={PATHS.quoteApprovals} element={<ApprovalListPage />} />
          <Route path={PATHS.quoteApproval} element={<ApprovalPage />} />
          <Route path={PATHS.quoteSettings} element={<QuoteSettingsPage />} />
          <Route path={PATHS.quoteSender} element={<SenderPage />} />
          <Route path={PATHS.peers} element={<PeersPage />} />
          <Route
            path={PATHS.organisations}
            element={
              <AdminOnly title="Organisaties">
                <OrganisationsAdminPage />
              </AdminOnly>
            }
          />
          <Route
            path={PATHS.roles}
            element={
              <AdminOnly title="Rollen">
                <RolesAdminPage />
              </AdminOnly>
            }
          />
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
    </PageBoundary>
  );
}
