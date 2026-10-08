import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { ApiError, errorMessage } from '@/api/client';
import { STATUS_COLORS, statusLabel } from '@/features/assignments/labels';
import { assignmentPath } from '@/features/assignments/paths';
import { EmptyNotice, ErrorNotice, Loading } from '@/features/assignments/ui';
import { TOTALS_COLUMNS, TotalsCells, TotalsHeaderCells } from '@/features/overview/TotalsCells';
import { hasAmounts } from '@/features/overview/api';
import { Segments } from '@/features/team/ui/controls';
import { RouterLinks } from '@/layout/RouterLinks';
import { useInstance } from '@/layout/useInstance';
import { formatDate, formatEuro, formatFte, formatPercent, formatPeriod } from '@/lib/format';
import { PageHeading } from '@/pages/PageHeading';
import { PATHS } from '@/paths';
import {
  assignmentReportDocumentUrl,
  fetchAssignmentReport,
  reportKeys,
  type AssignmentReport,
  type Audience,
} from './api';
import { ACCEPTANCE_FORM_LABELS, KIND_LABELS } from './labels';
import { MoneyCell, NumberCell, ReportBlock } from './ui';

function Facts({ report }: { report: AssignmentReport }) {
  const facts: [string, string][] = [
    ['Opdrachtgever', report.client_name ?? ''],
    ['Opdrachtnemer', report.contractor_name ?? ''],
    ['Looptijd', formatPeriod(report.start_date, report.end_date)],
    ['Soort', KIND_LABELS[report.kind] ?? report.kind],
    ['Kenmerk', report.uri],
    ['Context', (report.context_refs ?? []).join(', ')],
  ];
  return (
    <nldd-list accessible-label="Gegevens van de opdracht" appearance="box-base">
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

function AgreedBlock({ report }: { report: AssignmentReport }) {
  const agreed = report.agreed;
  if (agreed && 'total_cents' in agreed) {
    const form = agreed.form ? ACCEPTANCE_FORM_LABELS[agreed.form] : undefined;
    const sentences = [`Offerte uitgegeven op ${formatDate(agreed.issued_at)}.`];
    if (agreed.accepted_at) {
      sentences.push(`Akkoord op ${formatDate(agreed.accepted_at)}${form ? `, ${form}` : ''}.`);
    }
    const subtotals = agreed.subtotals ?? [];
    return (
      <ReportBlock testId="agreed" title="Wat is afgesproken" note={sentences.join(' ')}>
        <nldd-table
          accessible-label="De offerte waarop akkoord is gegeven"
          columns="minmax(220px,2fr) minmax(200px,1fr) 90px 150px"
        >
          <nldd-table-row slot="header">
            <nldd-text-cell text="Omschrijving" />
            <nldd-text-cell text="Periode" />
            <nldd-text-cell text="FTE" horizontal-alignment="right" />
            <nldd-text-cell text="Bedrag" horizontal-alignment="right" />
          </nldd-table-row>
          {(agreed.lines ?? []).map((line, index) => (
            <nldd-table-row key={`${line.description}-${index}`}>
              <nldd-text-cell
                text={line.description}
                {...(line.role && line.role !== line.description
                  ? { 'supporting-text': line.role }
                  : {})}
              />
              <nldd-text-cell text={formatPeriod(line.start_date, line.end_date)} />
              <NumberCell text={formatFte(line.fte)} />
              <MoneyCell cents={line.amount_cents} />
            </nldd-table-row>
          ))}
          {subtotals.length > 1 &&
            subtotals.map((subtotal) => (
              <nldd-table-row key={subtotal.year}>
                <nldd-text-cell text={`Subtotaal ${subtotal.year}`} />
                <nldd-text-cell />
                <nldd-text-cell />
                <MoneyCell cents={subtotal.amount_cents} />
              </nldd-table-row>
            ))}
          <nldd-table-row>
            <nldd-text-cell text="**Totaal afgesproken**" />
            <nldd-text-cell />
            <nldd-text-cell />
            <MoneyCell cents={agreed.total_cents} bold />
          </nldd-table-row>
        </nldd-table>
      </ReportBlock>
    );
  }
  // Without class B the API sends neither key; then there is nothing to say.
  if (!('agreed' in report) && !('quoted_amount_cents' in report)) return null;
  return (
    <ReportBlock testId="agreed" title="Wat is afgesproken">
      <nldd-text>
        Er is geen offerte waarop akkoord is gegeven.
        {typeof report.quoted_amount_cents === 'number'
          ? ` Het afgesproken bedrag is ${formatEuro(report.quoted_amount_cents)}.`
          : ''}
      </nldd-text>
    </ReportBlock>
  );
}

function DeliveredBlock({ report }: { report: AssignmentReport }) {
  const final = report.final_report;
  const history = report.status_history ?? [];
  return (
    <ReportBlock
      testId="delivered"
      title="Wat is geleverd"
      {...(report.months_total > 0
        ? {
            note: `Van de ${report.months_total} maanden van de opdracht zijn er ${report.months_closed} afgesloten met vastgestelde inzet.`,
          }
        : {})}
    >
      {final ? (
        <nldd-container gap="8">
          <nldd-text>Eindrapport van {formatDate(final.issued_at)}.</nldd-text>
          {final.summary && <nldd-text>{final.summary}</nldd-text>}
          <nldd-list accessible-label="Geleverd" appearance="box-base">
            {(final.delivered ?? []).length === 0 && (
              <nldd-list-item>
                <nldd-text-cell overline="Geleverd" text="Het eindrapport noemt niets." />
              </nldd-list-item>
            )}
            {(final.delivered ?? []).map((item) => (
              <nldd-list-item key={item}>
                <nldd-text-cell overline="Geleverd" text={item} />
              </nldd-list-item>
            ))}
          </nldd-list>
          <nldd-list accessible-label="Niet geleverd" appearance="box-base">
            {(final.not_delivered ?? []).length === 0 && (
              <nldd-list-item>
                <nldd-text-cell overline="Niet geleverd" text="Het eindrapport noemt niets." />
              </nldd-list-item>
            )}
            {(final.not_delivered ?? []).map((item) => (
              <nldd-list-item key={item}>
                <nldd-text-cell overline="Niet geleverd" text={item} />
              </nldd-list-item>
            ))}
          </nldd-list>
        </nldd-container>
      ) : (
        <EmptyNotice
          text="Er is nog geen eindrapport"
          supportingText="Het eindrapport wordt uitgegeven als de opdracht is afgerond."
        />
      )}
      {history.length > 0 && (
        <nldd-table accessible-label="Verloop van de status" columns="170px minmax(220px,1fr)">
          <nldd-table-row slot="header">
            <nldd-text-cell text="Datum" />
            <nldd-text-cell text="Status" />
          </nldd-table-row>
          {history.map((change, index) => (
            <nldd-table-row key={`${change.occurred_at}-${index}`}>
              <nldd-text-cell text={formatDate(change.occurred_at)} />
              <nldd-text-cell
                text={statusLabel(change.new_status)}
                {...(change.reason ? { 'supporting-text': change.reason } : {})}
              />
            </nldd-table-row>
          ))}
        </nldd-table>
      )}
    </ReportBlock>
  );
}

function CostBlock({ report }: { report: AssignmentReport }) {
  const periods = (report.periods ?? []).filter((period) => hasAmounts(period.totals));
  const lines = (report.lines ?? []).filter((line) => hasAmounts(line.totals));
  const costs = report.costs ?? [];
  if (!hasAmounts(report.totals) && !report.pricing_error) return null;
  return (
    <ReportBlock
      testId="cost"
      title="Wat het heeft gekost"
      note="Gerealiseerd is de vastgestelde inzet van afgesloten maanden. Prognose is de geplande inzet van open maanden."
    >
      {report.pricing_error && (
        <nldd-banner variant="warning" size="sm" text={report.pricing_error} />
      )}
      {(periods.length > 0 || hasAmounts(report.totals)) && (
        <nldd-table accessible-label="Kosten per jaar" columns={`minmax(160px,1fr) ${TOTALS_COLUMNS}`}>
          <nldd-table-row slot="header">
            <nldd-text-cell text="Periode" />
            <TotalsHeaderCells />
          </nldd-table-row>
          {periods.map((period) => (
            <nldd-table-row key={period.year}>
              <nldd-text-cell text={String(period.year)} />
              <TotalsCells totals={period.totals} error={period.pricing_error} />
            </nldd-table-row>
          ))}
          {hasAmounts(report.totals) && (
            <nldd-table-row>
              <nldd-text-cell text="**Hele looptijd**" />
              <TotalsCells totals={report.totals} bold />
            </nldd-table-row>
          )}
        </nldd-table>
      )}
      {lines.length > 0 && (
        <nldd-table
          accessible-label="Kosten per begrotingsregel, over de hele looptijd"
          columns={`minmax(200px,1fr) ${TOTALS_COLUMNS}`}
        >
          <nldd-table-row slot="header">
            <nldd-text-cell text="Begrotingsregel" />
            <TotalsHeaderCells />
          </nldd-table-row>
          {lines.map((line) => (
            <nldd-table-row key={line.budget_line_id}>
              <nldd-text-cell text={line.description} />
              <TotalsCells totals={line.totals} error={line.pricing_error} />
            </nldd-table-row>
          ))}
        </nldd-table>
      )}
      {costs.length > 0 && (
        <nldd-table
          accessible-label="Kosten en dekking"
          columns="minmax(200px,1.5fr) minmax(200px,1fr) 100px 150px"
        >
          <nldd-table-row slot="header">
            <nldd-text-cell text="Kostenpost" />
            <nldd-text-cell text="Gedekt door" />
            <nldd-text-cell text="Aandeel" horizontal-alignment="right" />
            <nldd-text-cell text="Bedrag" horizontal-alignment="right" />
          </nldd-table-row>
          {costs.map((cost, index) => (
            <nldd-table-row key={`${cost.cost_item_id}-${index}`}>
              <nldd-text-cell text={cost.description} />
              <nldd-text-cell text={cost.budget_line_description} />
              <NumberCell text={formatPercent(cost.pct)} />
              <MoneyCell cents={cost.amount_cents} />
            </nldd-table-row>
          ))}
        </nldd-table>
      )}
    </ReportBlock>
  );
}

function StaffingBlock({ report }: { report: AssignmentReport }) {
  const staffing = report.staffing ?? [];
  if (staffing.length === 0) return null;
  return (
    <ReportBlock
      testId="staffing"
      title="Wie eraan werkte"
      note="Alleen voor intern gebruik. Deze namen staan niet in de versie voor de opdrachtgever."
    >
      <nldd-table
        accessible-label="Wie aan de opdracht werkte"
        columns="minmax(180px,1.5fr) minmax(160px,1fr) minmax(200px,1fr) 100px"
      >
        <nldd-table-row slot="header">
          <nldd-text-cell text="Naam" />
          <nldd-text-cell text="Rol" />
          <nldd-text-cell text="Periode" />
          <nldd-text-cell text="Inzet" horizontal-alignment="right" />
        </nldd-table-row>
        {staffing.map((member, index) => (
          <nldd-table-row key={`${member.person_id}-${index}`}>
            <nldd-text-cell text={member.person_name} />
            <nldd-text-cell text={member.role ?? member.budget_line_description} />
            <nldd-text-cell text={formatPeriod(member.start_date, member.end_date)} />
            <NumberCell text={formatPercent(member.fte_pct)} />
          </nldd-table-row>
        ))}
      </nldd-table>
    </ReportBlock>
  );
}

/**
 * The report of one assignment: what was agreed, what was delivered and what
 * it cost. The version for the client never names staff; the internal one
 * adds who worked on it, as far as the reader may see that.
 */
export function AssignmentReportPage() {
  const { assignmentId = '' } = useParams();
  const instance = useInstance();
  const [audience, setAudience] = useState<Audience>('client');
  const query = useQuery({
    queryKey: reportKeys.assignment(assignmentId, audience),
    queryFn: () => fetchAssignmentReport(assignmentId, audience),
    enabled: assignmentId !== '',
  });
  const report = query.data;
  const notFound = query.error instanceof ApiError && query.error.status === 404;

  return (
    <nldd-simple-section>
      <PageHeading
        text={report ? `Rapportage ${report.name}` : 'Rapportage'}
        instanceName={instance?.name}
      />
      <nldd-container gap="24">
        <RouterLinks>
          <nldd-container layout="wrap" gap="16" vertical-alignment="center">
            <nldd-link href={PATHS.reports} text="Terug naar de rapportage" size="md" />
            {report && (
              <nldd-link href={assignmentPath(report.assignment_id)} text="Naar de opdracht" size="md" />
            )}
          </nldd-container>
        </RouterLinks>
        {query.isPending && <Loading />}
        {query.isError &&
          (notFound ? (
            <EmptyNotice
              text="Deze opdracht is niet gevonden"
              supportingText="De opdracht bestaat niet, of je bent er niet bij betrokken."
            />
          ) : (
            <ErrorNotice message={errorMessage(query.error)} />
          ))}
        {report && (
          <>
            <nldd-container layout="wrap" gap="12" vertical-alignment="center">
              <nldd-badge
                color={STATUS_COLORS[report.status] ?? 'neutral'}
                text={statusLabel(report.status)}
              />
              <Segments
                label="Versie"
                value={audience}
                onChange={(next) => setAudience(next === 'internal' ? 'internal' : 'client')}
                options={[
                  { value: 'client', label: 'Voor de opdrachtgever' },
                  { value: 'internal', label: 'Intern' },
                ]}
              />
              <nldd-link
                href={assignmentReportDocumentUrl(report.assignment_id, audience)}
                text="Afdrukbare versie"
                size="md"
                target="_blank"
              />
            </nldd-container>
            <Facts report={report} />
            <AgreedBlock report={report} />
            <DeliveredBlock report={report} />
            <CostBlock report={report} />
            {audience === 'internal' && <StaffingBlock report={report} />}
          </>
        )}
      </nldd-container>
    </nldd-simple-section>
  );
}
