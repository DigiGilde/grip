import { BackLink } from '@/ui/Icon';
import { useRef, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { ApiError, errorMessage } from '@/api/client';
import { STATUS_COLORS, statusLabel } from '@/features/assignments/labels';
import { Button } from '@/features/assignments/ui';
import {
  EmptyNotice,
  ErrorNotice,
  LoadError,
  Loading,
  SectionHeading,
  NotFound,
} from '@/ui/layout';
import { AssignmentContextView } from '@/features/nodes';
import { QUOTE_STATUS_COLORS, QUOTE_STATUS_LABELS } from '@/features/quotes/api';
import { formatDateTime } from '@/features/quotes/format';
import { useCaseCourse } from '@/features/tasks/course';
import { useInstance } from '@/layout/useInstance';
import { useRouterLinks } from '@/layout/useRouterLinks';
import { formatDate, formatEuro, formatPeriod } from '@/lib/format';
import { PageHeading } from '@/pages/PageHeading';
import { courseAction } from '@/ui/course';
import { CourseBar, CourseNow } from '@/ui/Workflow';
import {
  clientKeys,
  fetchClientAssignment,
  fetchFinalReport,
  fetchProgress,
  requestBudgetUsage,
  type BudgetUsage,
  type ClientAssignmentDetail,
  type FinalReport,
  type Progress,
} from './api';
import { MILESTONE_STATE_LABELS, deliveryText } from './labels';
import { clientPath, receivedQuotePath } from './paths';
import './register';

function Facts({ assignment }: { assignment: ClientAssignmentDetail }) {
  const facts: [string, string][] = [
    ['Opdrachtnemer', assignment.contractor_name ?? ''],
    ['Gewenste periode', formatPeriod(assignment.start_date, assignment.end_date)],
    ['Aangevraagd op', formatDateTime(assignment.created_at)],
    ['Verzending van de aanvraag', deliveryText(assignment.request_delivery)],
    ['Wat is gevraagd', assignment.description ?? ''],
  ];
  return (
    <nldd-list accessible-label="Gegevens van de aanvraag" appearance="box-base">
      {facts
        .filter(([, value]) => value !== '')
        .map(([label, value]) => (
          <nldd-list-item key={label}>
            <nldd-text-cell overline={label} text={value} />
          </nldd-list-item>
        ))}
    </nldd-list>
  );
}

function Quotes({ assignment }: { assignment: ClientAssignmentDetail }) {
  const quotes = assignment.quotes ?? [];
  const showAmounts = quotes.some((quote) => 'total_cents' in quote);
  if (quotes.length === 0) {
    return (
      <EmptyNotice
        text="Er is nog geen offerte ontvangen"
        supportingText="De offerte verschijnt hier zodra de opdrachtnemer hem heeft uitgegeven."
      />
    );
  }
  return (
    <nldd-table
      accessible-label="Offertes op deze aanvraag"
      columns={`minmax(200px,1fr) 190px${showAmounts ? ' 150px' : ''}`}
    >
      <nldd-table-row slot="header">
        <nldd-text-cell text="Uitgegeven" />
        <nldd-text-cell text="Status" />
        {showAmounts ? <nldd-text-cell text="Bedrag" horizontal-alignment="right" /> : null}
      </nldd-table-row>
      {quotes.map((quote) => (
        <nldd-table-row key={quote.id}>
          <nldd-cell>
            <nldd-link href={receivedQuotePath(quote.id)} text={formatDateTime(quote.issued_at)} />
          </nldd-cell>
          <nldd-cell>
            <nldd-badge
              color={QUOTE_STATUS_COLORS[quote.status] ?? 'neutral'}
              text={QUOTE_STATUS_LABELS[quote.status] ?? quote.status}
            />
          </nldd-cell>
          {showAmounts ? (
            <nldd-text-cell text={formatEuro(quote.total_cents)} horizontal-alignment="right" />
          ) : null}
        </nldd-table-row>
      ))}
    </nldd-table>
  );
}

function ProgressView({ progress }: { progress: Progress }) {
  if (!progress.available) {
    return (
      <nldd-banner
        variant="neutral"
        size="sm"
        text="De voortgang is nu niet op te vragen"
        supporting-text={progress.problem ?? ''}
      />
    );
  }
  const milestones = progress.milestones ?? [];
  const delivered = progress.delivered ?? [];
  const notDelivered = progress.not_delivered ?? [];
  return (
    <nldd-container gap="16">
      <nldd-text>
        Status bij de opdrachtnemer: {statusLabel(progress.status ?? '')}
        {progress.as_of ? `, per ${formatDate(progress.as_of)}` : ''}. Opgevraagd op{' '}
        {formatDateTime(progress.fetched_at)}.
      </nldd-text>
      {progress.summary ? <nldd-text>{progress.summary}</nldd-text> : null}
      {milestones.length > 0 ? (
        <nldd-table accessible-label="Mijlpalen" columns="minmax(220px,2fr) 160px 140px">
          <nldd-table-row slot="header">
            <nldd-text-cell text="Mijlpaal" />
            <nldd-text-cell text="Streefdatum" />
            <nldd-text-cell text="Stand" />
          </nldd-table-row>
          {milestones.map((milestone, index) => (
            <nldd-table-row key={`${milestone.description}-${index}`}>
              <nldd-text-cell text={milestone.description} />
              <nldd-text-cell text={formatDate(milestone.due_date)} />
              <nldd-text-cell
                text={MILESTONE_STATE_LABELS[milestone.state ?? ''] ?? milestone.state ?? ''}
              />
            </nldd-table-row>
          ))}
        </nldd-table>
      ) : null}
      {delivered.length > 0 ? <nldd-text>Geleverd: {delivered.join('; ')}.</nldd-text> : null}
      {notDelivered.length > 0 ? (
        <nldd-text>Niet geleverd: {notDelivered.join('; ')}.</nldd-text>
      ) : null}
    </nldd-container>
  );
}

function UsageView({ usage }: { usage: BudgetUsage }) {
  if (!usage.available) {
    return (
      <nldd-banner
        variant={usage.not_in_contract ? 'warning' : 'neutral'}
        size="sm"
        text={
          usage.not_in_contract
            ? 'De uitputting valt niet onder het contract'
            : 'De uitputting is nu niet op te vragen'
        }
        supporting-text={usage.problem ?? ''}
      />
    );
  }
  const lines = usage.lines ?? [];
  return (
    <nldd-container gap="16">
      <nldd-text aria-live="polite">
        Opgevraagd op {formatDateTime(usage.fetched_at)}
        {usage.as_of ? `, stand per ${formatDate(usage.as_of)}` : ''}
        {usage.year ? `, over ${usage.year}` : ', over de hele looptijd'}.
      </nldd-text>
      <nldd-table
        accessible-label="Uitputting volgens de opdrachtnemer"
        columns="minmax(220px,2fr) 150px 150px 150px"
      >
        <nldd-table-row slot="header">
          <nldd-text-cell text="Begrotingsregel" />
          <nldd-text-cell text="Begroot" horizontal-alignment="right" />
          <nldd-text-cell text="Uitputting" horizontal-alignment="right" />
          <nldd-text-cell text="Afwijking" horizontal-alignment="right" />
        </nldd-table-row>
        {lines.map((line, index) => (
          <nldd-table-row key={`${line.description}-${index}`}>
            <nldd-text-cell
              text={line.description}
              {...((line.available_cents ?? 0) < 0 ? { 'supporting-text': 'Overschreden' } : {})}
            />
            <nldd-text-cell text={formatEuro(line.budgeted_cents)} horizontal-alignment="right" />
            <nldd-text-cell text={formatEuro(line.used_cents)} horizontal-alignment="right" />
            <nldd-text-cell text={formatEuro(line.available_cents)} horizontal-alignment="right" />
          </nldd-table-row>
        ))}
        <nldd-table-row>
          <nldd-text-cell
            text="Totaal"
            {...((usage.available_cents ?? 0) < 0 ? { 'supporting-text': 'Overschreden' } : {})}
          />
          <nldd-text-cell text={formatEuro(usage.budgeted_cents)} horizontal-alignment="right" />
          <nldd-text-cell text={formatEuro(usage.used_cents)} horizontal-alignment="right" />
          <nldd-text-cell text={formatEuro(usage.available_cents)} horizontal-alignment="right" />
        </nldd-table-row>
      </nldd-table>
    </nldd-container>
  );
}

function FinalReportView({ report }: { report: FinalReport }) {
  const notDelivered = report.not_delivered ?? [];
  const facts: [string, string][] = [
    ['Ontvangen op', formatDateTime(report.received_at)],
    ['Periode', formatPeriod(report.period_start, report.period_end)],
    ['Afgesproken', (report.agreed ?? []).join('; ')],
    ['Geleverd', (report.delivered ?? []).join('; ')],
    ['Kosten', 'total_cost_cents' in report ? formatEuro(report.total_cost_cents) : ''],
  ];
  return (
    <nldd-container gap="16">
      {report.summary ? <nldd-text>{report.summary}</nldd-text> : null}
      <nldd-list accessible-label="Eindrapport" appearance="box-base">
        {facts
          .filter(([, value]) => value !== '')
          .map(([label, value]) => (
            <nldd-list-item key={label}>
              <nldd-text-cell overline={label} text={value} />
            </nldd-list-item>
          ))}
      </nldd-list>
      {notDelivered.length > 0 ? (
        <nldd-table accessible-label="Niet geleverd" columns="minmax(220px,1fr) minmax(220px,1fr)">
          <nldd-table-row slot="header">
            <nldd-text-cell text="Niet geleverd" />
            <nldd-text-cell text="Reden" />
          </nldd-table-row>
          {notDelivered.map((item, index) => (
            <nldd-table-row key={`${item.description}-${index}`}>
              <nldd-text-cell text={item.description} />
              <nldd-text-cell text={item.reason ?? ''} />
            </nldd-table-row>
          ))}
        </nldd-table>
      ) : null}
    </nldd-container>
  );
}

/** One assignment this organisation asked for: the request, its quotes, and how it goes. */
export function ClientAssignmentPage() {
  const { assignmentId = '' } = useParams();
  const instance = useInstance();
  const ref = useRef<HTMLDivElement>(null);
  useRouterLinks(ref);

  const query = useQuery({
    queryKey: clientKeys.assignment(assignmentId),
    queryFn: () => fetchClientAssignment(assignmentId),
    retry: false,
  });
  const assignment = query.data;
  const reachable = assignment?.contractor_reachable === true;

  const progress = useQuery({
    queryKey: clientKeys.progress(assignmentId),
    queryFn: () => fetchProgress(assignmentId),
    enabled: reachable,
    retry: false,
  });
  const report = useQuery({
    queryKey: clientKeys.finalReport(assignmentId),
    queryFn: () => fetchFinalReport(assignmentId),
    enabled: assignment !== undefined,
    retry: false,
  });

  // Spending is asked only on a click, and the answer is kept for this visit.
  const [usage, setUsage] = useState<BudgetUsage | null>(null);
  const [usageError, setUsageError] = useState<string | null>(null);
  const askUsage = useMutation({
    mutationFn: () => requestBudgetUsage(assignmentId, null),
    onSuccess: (answer) => {
      setUsage(answer);
      setUsageError(null);
    },
    onError: (failure) => setUsageError(errorMessage(failure)),
  });

  const notFound = query.error instanceof ApiError && query.error.status === 404;
  const course = useCaseCourse('assignment', assignmentId, query.isSuccess).data?.course;
  const step = courseAction(course);

  return (
    <div ref={ref}>
      <nldd-simple-section>
        <PageHeading text={assignment?.name ?? 'Aanvraag'} instanceName={instance?.name} />
        <nldd-container gap="16">
          <BackLink href={clientPath()} text="Terug naar aanvragen" />
          {query.isPending ? <Loading /> : null}
          {query.isError && notFound ? <NotFound what="Deze aanvraag" /> : null}
          {query.isError && !notFound ? (
            <LoadError error={query.error} retry={() => void query.refetch()} />
          ) : null}
          {assignment ? (
            <>
              {/* Where the request stands and whose move it is, as on the
                  contractor's side: the same course, read as the client. */}
              {course ? <CourseNow course={course} /> : null}
              {step ? (
                <nldd-button-group>
                  <Button appearance="primary" text={step.text} href={step.href} />
                </nldd-button-group>
              ) : null}
              {course && !course.ended ? (
                <CourseBar course={course} accessibleLabel={`Verloop van ${assignment.name}`} />
              ) : (
                <div>
                  <nldd-badge
                    color={STATUS_COLORS[assignment.status] ?? 'neutral'}
                    text={course?.ended ?? statusLabel(assignment.status)}
                  />
                </div>
              )}
              <Facts assignment={assignment} />
            </>
          ) : null}
        </nldd-container>
      </nldd-simple-section>

      {assignment ? (
        <>
          <nldd-simple-section>
            <SectionHeading text="Context" />
            <AssignmentContextView
              assignmentId={assignment.id}
              count={(assignment.context_refs ?? []).length}
            />
          </nldd-simple-section>

          <nldd-simple-section>
            <SectionHeading text="Offertes" />
            <Quotes assignment={assignment} />
          </nldd-simple-section>

          <nldd-simple-section>
            <SectionHeading text="Voortgang" />
            {!reachable ? (
              <EmptyNotice
                text="De voortgang is hier niet op te vragen"
                supportingText="De opdrachtnemer werkt niet met grip, of jullie grip is er niet mee gekoppeld."
              />
            ) : null}
            {reachable && progress.isPending ? (
              <Loading text="Bezig met opvragen bij de opdrachtnemer" />
            ) : null}
            {progress.isError ? (
              <LoadError error={progress.error} retry={() => void progress.refetch()} />
            ) : null}
            {progress.data ? <ProgressView progress={progress.data} /> : null}
          </nldd-simple-section>

          {assignment.may_request_usage ? (
            <nldd-simple-section>
              <SectionHeading text="Uitputting" />
              <nldd-container gap="16">
                <nldd-text>
                  De uitputting haal je alleen op als je erom vraagt. De opdrachtnemer geeft de
                  cijfers als financiële inzage onderdeel is van het contract. Elke opvraging wordt
                  vastgelegd.
                </nldd-text>
                <div>
                  <Button
                    text={usage ? 'Vraag de uitputting opnieuw op' : 'Vraag de uitputting op'}
                    loading={askUsage.isPending}
                    onClick={() => askUsage.mutate()}
                  />
                </div>
                {usageError ? <ErrorNotice message={usageError} /> : null}
                {usage ? <UsageView usage={usage} /> : null}
              </nldd-container>
            </nldd-simple-section>
          ) : null}

          {report.data?.received ? (
            <nldd-simple-section>
              <SectionHeading text="Eindrapport" />
              <FinalReportView report={report.data} />
            </nldd-simple-section>
          ) : null}
        </>
      ) : null}
    </div>
  );
}
