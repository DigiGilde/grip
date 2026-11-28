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
import { ASSIGNMENT_PART_SEGMENTS } from '@/features/assignments/paths';
import { StartPage } from '@/features/start/StartPage';
import { TasksPage } from '@/features/tasks/TasksPage';
import { VACANCY_PART_SEGMENTS } from '@/features/vacancies/paths';
import { page, preloadFor } from '@/pageChunks';
import type { ReactElement } from 'react';

// The shell, the start page and the tasks come with the first load. Every
// page below is a file of its own, fetched on the way to it (see
// `pageChunks`): the patterns say for which addresses.
const ASSIGNMENT = `${PATHS.assignmentDetail}/*`;
const VACANCY = `${PATHS.vacancyDetail}/*`;
const assignmentPart = (segment: string) => `${PATHS.assignmentDetail}/${segment}`;
const vacancyPart = (segment: string) => `${PATHS.vacancyDetail}/${segment}`;

const AdminPage = page(() => import('@/pages/AdminPage'), 'AdminPage', PATHS.admin);
const AllocationsPage = page(
  () => import('@/features/allocations/AllocationsPage'),
  'AllocationsPage',
  PATHS.peopleBoard,
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
const AssignmentLanding = page(
  () => import('@/features/assignments/AssignmentLanding'),
  'AssignmentLanding',
  PATHS.assignmentDetail,
);
const ClosePart = page(
  () => import('@/features/assignments/parts/ClosePart'),
  'ClosePart',
  assignmentPart(ASSIGNMENT_PART_SEGMENTS.close),
);
const BudgetPart = page(
  () => import('@/features/assignments/parts/BudgetPart'),
  'BudgetPart',
  assignmentPart(ASSIGNMENT_PART_SEGMENTS.budget),
);
const QuotePart = page(
  () => import('@/features/assignments/parts/QuotePart'),
  'QuotePart',
  assignmentPart(ASSIGNMENT_PART_SEGMENTS.quote),
);
const TeamPart = page(
  () => import('@/features/assignments/parts/TeamPart'),
  'TeamPart',
  assignmentPart(ASSIGNMENT_PART_SEGMENTS.team),
);
const ReportPart = page(
  () => import('@/features/assignments/parts/ReportPart'),
  'ReportPart',
  assignmentPart(ASSIGNMENT_PART_SEGMENTS.report),
);
const AssignmentDetailsPart = page(
  () => import('@/features/assignments/parts/DetailsPart'),
  'DetailsPart',
  assignmentPart(ASSIGNMENT_PART_SEGMENTS.details),
);
const AssignmentHistoryPart = page(
  () => import('@/features/assignments/parts/HistoryPart'),
  'HistoryPart',
  assignmentPart(ASSIGNMENT_PART_SEGMENTS.history),
);
const AssignmentTasksPart = page(
  () => import('@/features/assignments/parts/TasksPart'),
  'TasksPart',
  assignmentPart(ASSIGNMENT_PART_SEGMENTS.tasks),
);
const ActivityPage = page(
  () => import('@/features/history/History'),
  'ActivityPage',
  PATHS.activity,
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
const RetentionPage = page(
  () => import('@/features/retention/RetentionPage'),
  'RetentionPage',
  PATHS.retention,
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
const PeersPage = page(
  () => import('@/features/peers/PeersPage'),
  'PeersPage',
  PATHS.peers,
  PATHS.peer,
);
const RatesPage = page(() => import('@/features/rates/RatesPage'), 'RatesPage', PATHS.rates);
const MePage = page(() => import('@/layout/MePage'), 'MePage', PATHS.me);
const SearchPage = page(() => import('@/features/search/SearchPage'), 'SearchPage', PATHS.search);
const MoneyPage = page(() => import('@/features/money/MoneyPage'), 'MoneyPage', PATHS.money);
const RunningAssignmentsPage = page(
  () => import('@/features/money/RunningAssignmentsPage'),
  'RunningAssignmentsPage',
  PATHS.moneyAssignments,
);
const TurnoverPage = page(
  () => import('@/features/money/TurnoverPage'),
  'TurnoverPage',
  PATHS.moneyTurnover,
);
const InvestmentPage = page(
  () => import('@/features/money/InvestmentPage'),
  'InvestmentPage',
  PATHS.moneyInvestment,
);
const PotentialPage = page(
  () => import('@/features/money/PotentialPage'),
  'PotentialPage',
  PATHS.moneyPotential,
);
const YearAccountPage = page(
  () => import('@/features/money/YearAccountPage'),
  'YearAccountPage',
  PATHS.yearAccount,
);
const PeoplePage = page(() => import('@/features/team/PeoplePage'), 'PeoplePage', PATHS.people);
const OccupancyPage = page(
  () => import('@/features/team/OccupancyPage'),
  'OccupancyPage',
  PATHS.peopleOccupancy,
);
const BillabilityPage = page(
  () => import('@/features/team/BillabilityPage'),
  'BillabilityPage',
  PATHS.peopleBillability,
);
const PersonPage = page(() => import('@/features/team/PersonPage'), 'PersonPage', PATHS.person);
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
const PublishedPage = page(
  () => import('@/features/vacancies/PublishedPage'),
  'PublishedPage',
  PATHS.vacancyPublished,
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
const VacancyLanding = page(
  () => import('@/features/vacancies/VacancyLanding'),
  'VacancyLanding',
  PATHS.vacancyDetail,
);
const RequestPart = page(
  () => import('@/features/vacancies/parts/RequestPart'),
  'RequestPart',
  vacancyPart(VACANCY_PART_SEGMENTS.request),
);
const DecisionsPart = page(
  () => import('@/features/vacancies/parts/DecisionsPart'),
  'DecisionsPart',
  vacancyPart(VACANCY_PART_SEGMENTS.decisions),
);
const TextPart = page(
  () => import('@/features/vacancies/parts/TextPart'),
  'TextPart',
  vacancyPart(VACANCY_PART_SEGMENTS.text),
);
const FulfilmentPart = page(
  () => import('@/features/vacancies/parts/FulfilmentPart'),
  'FulfilmentPart',
  vacancyPart(VACANCY_PART_SEGMENTS.fulfilment),
);
const VacancyDetailsPart = page(
  () => import('@/features/vacancies/parts/DetailsPart'),
  'DetailsPart',
  vacancyPart(VACANCY_PART_SEGMENTS.details),
);
const VacancyHistoryPart = page(
  () => import('@/features/vacancies/parts/HistoryPart'),
  'HistoryPart',
  vacancyPart(VACANCY_PART_SEGMENTS.history),
);
const VacancyTasksPart = page(
  () => import('@/features/vacancies/parts/TasksPart'),
  'TasksPart',
  vacancyPart(VACANCY_PART_SEGMENTS.tasks),
);
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
  [PATHS.start]: <StartPage />,
  [PATHS.tasks]: <TasksPage />,
  [PATHS.assignments]: <AssignmentsPage />,
  [PATHS.people]: <PeoplePage />,
  [PATHS.vacancies]: <VacanciesPage />,
  [PATHS.money]: <MoneyPage />,
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
    <PageBoundary resetKey={pathname}>
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
          {/* One assignment: a shared header around one page per part. */}
          <Route path={PATHS.assignmentDetail} element={<AssignmentLayout />}>
            <Route index element={<AssignmentLanding />} />
            <Route path={ASSIGNMENT_PART_SEGMENTS.close} element={<ClosePart />} />
            <Route path={ASSIGNMENT_PART_SEGMENTS.budget} element={<BudgetPart />} />
            <Route path={ASSIGNMENT_PART_SEGMENTS.quote} element={<QuotePart />} />
            <Route path={ASSIGNMENT_PART_SEGMENTS.team} element={<TeamPart />} />
            <Route path={ASSIGNMENT_PART_SEGMENTS.report} element={<ReportPart />} />
            <Route path={ASSIGNMENT_PART_SEGMENTS.details} element={<AssignmentDetailsPart />} />
            <Route path={ASSIGNMENT_PART_SEGMENTS.history} element={<AssignmentHistoryPart />} />
            <Route path={ASSIGNMENT_PART_SEGMENTS.tasks} element={<AssignmentTasksPart />} />
          </Route>
          <Route path={PATHS.activity} element={<ActivityPage />} />
          <Route path={PATHS.updates} element={<UpdatesPage />} />
          <Route path={PATHS.search} element={<SearchPage />} />
          <Route path={PATHS.me} element={<MePage />} />
          <Route path={PATHS.peopleBoard} element={<AllocationsPage />} />
          <Route path={PATHS.peopleOccupancy} element={<OccupancyPage />} />
          <Route path={PATHS.peopleBillability} element={<BillabilityPage />} />
          <Route path={PATHS.moneyAssignments} element={<RunningAssignmentsPage />} />
          <Route path={PATHS.moneyTurnover} element={<TurnoverPage />} />
          <Route path={PATHS.moneyInvestment} element={<InvestmentPage />} />
          <Route path={PATHS.moneyPotential} element={<PotentialPage />} />
          <Route path={PATHS.costs} element={<CostsPage />} />
          <Route path={PATHS.billing} element={<BillingPage />} />
          <Route path={PATHS.yearAccount} element={<YearAccountPage />} />
          <Route path={PATHS.vacancyPublished} element={<PublishedPage />} />
          <Route path={PATHS.vacancySetup} element={<VacancySetupPage />} />
          <Route path={PATHS.languageModel} element={<LanguageModelPage />} />
          <Route path={PATHS.vacancyStandardTexts} element={<StandardTextsPage />} />
          <Route path={PATHS.formTemplate} element={<FormTemplatePage />} />
          <Route path={PATHS.functionFramework} element={<FunctionFrameworkPage />} />
          {/* One vacancy: a shared header with the steps, and a page per part. */}
          <Route path={PATHS.vacancyDetail} element={<VacancyLayout />}>
            <Route index element={<VacancyLanding />} />
            <Route path={VACANCY_PART_SEGMENTS.request} element={<RequestPart />} />
            <Route path={VACANCY_PART_SEGMENTS.decisions} element={<DecisionsPart />} />
            <Route path={VACANCY_PART_SEGMENTS.text} element={<TextPart />} />
            <Route path={VACANCY_PART_SEGMENTS.fulfilment} element={<FulfilmentPart />} />
            <Route path={VACANCY_PART_SEGMENTS.details} element={<VacancyDetailsPart />} />
            <Route path={VACANCY_PART_SEGMENTS.history} element={<VacancyHistoryPart />} />
            <Route path={VACANCY_PART_SEGMENTS.tasks} element={<VacancyTasksPart />} />
          </Route>
          {/* Writing the vacancy text is a page of its own, outside the parts. */}
          <Route path={PATHS.vacancyTextWrite} element={<VacancyTextPage />} />
          <Route path={PATHS.clientRequest} element={<RequestQuotePage />} />
          <Route path={PATHS.clientAssignment} element={<ClientAssignmentPage />} />
          <Route path={PATHS.receivedQuote} element={<ReceivedQuotePage />} />
          <Route path={PATHS.assignmentQuoteDraft} element={<QuoteDraftPage />} />
          <Route path={PATHS.quoteApprovals} element={<ApprovalListPage />} />
          <Route path={PATHS.quoteApproval} element={<ApprovalPage />} />
          <Route path={PATHS.quoteSettings} element={<QuoteSettingsPage />} />
          <Route path={PATHS.quoteSender} element={<SenderPage />} />
          <Route
            path={PATHS.retention}
            element={
              <AdminOnly title="Bewaartermijnen">
                <RetentionPage />
              </AdminOnly>
            }
          />
          {/* One route for the list and an open peer, so opening one keeps the list. */}
          <Route path={`${PATHS.peers}/:peerId?`} element={<PeersPage />} />
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
          <Route path={PATHS.person} element={<PersonPage />} />
          <Route path={PATHS.costItem} element={<CostItemPage />} />
          <Route path={PATHS.billingDelivery} element={<DeliveryPage />} />
          <Route path={PATHS.security} element={<SecurityPage />} />
          <Route path={PATHS.notifications} element={<NotificationsPage />} />
          <Route path={PATHS.wiesProposals} element={<WiesProposalsPage />} />
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
