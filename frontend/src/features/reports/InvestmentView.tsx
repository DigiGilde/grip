import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { errorMessage } from '@/api/client';
import { formatEuro, formatFte } from '@/lib/format';
import { EmptyNotice, ErrorNotice, Loading, Quiet } from '@/ui/layout';
import {
  fetchInvestment,
  reportKeys,
  type InvestmentMoney,
  type InvestmentTime,
} from './api';
import { monthName } from './labels';
import { topicPath } from './topics';
import { MoneyCell, NumberCell, ReportBlock } from './ui';

const count = (number: number, one: string, many: string) =>
  `${number} ${number === 1 ? one : many}`;

/** An amount that is taken off: written with a minus, a zero without. */
const minus = (cents: number) => (cents === 0 ? formatEuro(0) : `− ${formatEuro(cents)}`);

/**
 * The money reading as a derivation a reader can follow: what is expected
 * to come in, what is taken off, and what is left. Each line is the way
 * into the view that explains it.
 */
function MoneyDerivation({ money, year }: { money: InvestmentMoney; year: number }) {
  const y = String(year);
  const hasVerbal = money.verbal_cents > 0;
  const zero = (cents: number) => (cents === 0 ? 'grip-derivation__zero' : undefined);
  return (
    <table className="grip-derivation" data-testid="investment-money">
      <caption>Investeerruimte in geld, {year}</caption>
      <tbody>
        <tr>
          <th scope="row">
            <Link to={topicPath('omzet', y)}>Verwachte omzet van externe opdrachten</Link>
            <span className="grip-derivation__sub">
              {formatEuro(money.realised_cents)} gerealiseerd, {formatEuro(money.planned_cents)}{' '}
              nog gepland
              {hasVerbal ? `, waarvan ${formatEuro(money.verbal_cents)} op mondeling akkoord` : ''}
            </span>
          </th>
          <td>{formatEuro(money.expected_cents)}</td>
        </tr>
        <tr className={zero(money.target_cents)}>
          <th scope="row">
            <Link to={topicPath('declarabiliteit', y)}>Declarabiliteitstargets</Link>
            <span className="grip-derivation__sub">
              {money.target_person_count === 0
                ? 'niemand heeft een target'
                : `wat ${count(money.target_person_count, 'persoon', 'mensen')} samen ${
                    money.target_person_count === 1 ? 'moet' : 'moeten'
                  } binnenbrengen`}
            </span>
          </th>
          <td>{minus(money.target_cents)}</td>
        </tr>
        <tr className={zero(money.uncovered_cents)}>
          <th scope="row">
            <Link to={topicPath('kosten', y)}>Ongedekte kosten</Link>
            <span className="grip-derivation__sub">kosten die geen begrotingsregel dekt</span>
          </th>
          <td>{minus(money.uncovered_cents)}</td>
        </tr>
        <tr className={zero(money.internal_budget_cents)}>
          <th scope="row">
            <Link to={topicPath('jaarverantwoording', y)}>Begroot voor interne opdrachten</Link>
            <span className="grip-derivation__sub">
              {count(money.internal_count, 'interne opdracht', 'interne opdrachten')} met akkoord
            </span>
          </th>
          <td>{minus(money.internal_budget_cents)}</td>
        </tr>
        <tr className="grip-derivation__total">
          <th scope="row">
            {money.shortfall ? (
              <>
                <span className="grip-mark" aria-hidden="true">
                  !
                </span>{' '}
                Tekort
              </>
            ) : (
              'Investeerruimte'
            )}
          </th>
          <td data-testid="investment-room">
            {formatEuro(money.shortfall ? Math.abs(money.room_cents) : money.room_cents)}
          </td>
        </tr>
        {money.pipeline_cents > 0 && (
          <tr className="grip-derivation__apart">
            <th scope="row">
              <Link to={topicPath('pijplijn', y)}>Als de pijplijn doorgaat</Link>
              <span className="grip-derivation__sub">
                {formatEuro(money.pipeline_cents)} gepland op opdrachten zonder akkoord, telt niet
                mee
              </span>
            </th>
            <td>
              {money.room_with_pipeline_cents < 0
                ? `tekort ${formatEuro(Math.abs(money.room_with_pipeline_cents))}`
                : formatEuro(money.room_with_pipeline_cents)}
            </td>
          </tr>
        )}
      </tbody>
    </table>
  );
}

function MoneyMonths({ money, year }: { money: InvestmentMoney; year: number }) {
  const months = money.months ?? [];
  const withTargets = months.some((month) => month.target_cents !== null);
  return (
    <nldd-table
      accessible-label={`Omzet van externe opdrachten per maand in ${year}`}
      columns={`minmax(140px,1fr) 150px 150px${withTargets ? ' 150px 170px' : ''}`}
    >
      <nldd-table-row slot="header">
        <nldd-text-cell text="Maand" />
        <nldd-text-cell text="Gerealiseerd" horizontal-alignment="right" />
        <nldd-text-cell text="Nog gepland" horizontal-alignment="right" />
        {withTargets && (
          <>
            <nldd-text-cell text="Targets" horizontal-alignment="right" />
            <nldd-text-cell text="Omzet min targets" horizontal-alignment="right" />
          </>
        )}
      </nldd-table-row>
      {months.map((month) => (
        <nldd-table-row key={month.month}>
          <nldd-text-cell text={monthName(month.month)} />
          <MoneyCell cents={month.realised_cents} />
          <MoneyCell cents={month.planned_cents} />
          {withTargets && (
            <>
              <MoneyCell cents={month.target_cents} />
              <MoneyCell
                cents={month.turnover_minus_target_cents}
                {...((month.turnover_minus_target_cents ?? 0) < 0
                  ? { critical: true, note: 'Onder de targets' }
                  : {})}
              />
            </>
          )}
        </nldd-table-row>
      ))}
      <nldd-table-row>
        <nldd-text-cell text="**Totaal**" />
        <MoneyCell cents={money.realised_cents} bold />
        <MoneyCell cents={money.planned_cents} bold />
        {withTargets && (
          <>
            <MoneyCell cents={money.target_cents} bold />
            <nldd-text-cell />
          </>
        )}
      </nldd-table-row>
    </nldd-table>
  );
}

/** The time reading: free capacity per month, in FTE and, for who may see rates, in money. */
function TimeReading({ time }: { time: InvestmentTime }) {
  const months = time.months ?? [];
  const valued = 'value_cents' in time;
  const unvalued = months.reduce((most, month) => Math.max(most, month.unvalued_count ?? 0), 0);
  return (
    <nldd-container gap="8" data-testid="investment-time">
      <nldd-title size={5} text="Investeerruimte in tijd" heading-level={3} />
      <nldd-table
        accessible-label="Vrije capaciteit in de komende maanden"
        columns={`minmax(130px,1fr) 100px${valued ? ' 150px' : ''}`}
      >
        <nldd-table-row slot="header">
          <nldd-text-cell text="Maand" />
          <nldd-text-cell text="Vrij (FTE)" horizontal-alignment="right" />
          {valued && <nldd-text-cell text="Tegen inzettarief" horizontal-alignment="right" />}
        </nldd-table-row>
        {months.map((month) => (
          <nldd-table-row key={month.month}>
            <nldd-text-cell text={monthName(month.month)} />
            <NumberCell text={formatFte(month.free_fte)} muted={Number(month.free_fte) === 0} />
            {valued && <MoneyCell cents={month.value_cents} />}
          </nldd-table-row>
        ))}
      </nldd-table>
      <Quiet>
        Wat geteld is: de capaciteit die deze maand en de drie maanden erna niet is ingepland, van{' '}
        {count(time.person_count, 'inzetbare persoon', 'inzetbare mensen')}
        {valued ? ', gewaardeerd tegen het inzettarief van elke persoon in die maand' : ''}.
        Iedereen telt als voltijds, tot er een deeltijdfactor per persoon is.
        {valued && unvalued > 0
          ? ` Van ${count(unvalued, 'persoon', 'mensen')} is het tarief onbekend; hun ruimte zit wel in de FTE en niet in het bedrag.`
          : ''}
      </Quiet>
    </nldd-container>
  );
}

/**
 * Investeerruimte: what is left to invest, in money for the year and in
 * time for the coming months. The definition is provisional, so each
 * reading says in one quiet line what it counts.
 */
export function InvestmentView({ year, bare }: { year: string; bare?: boolean }) {
  const query = useQuery({
    queryKey: reportKeys.investment(year),
    queryFn: () => fetchInvestment(year),
  });
  if (query.isPending) return <Loading />;
  if (query.isError) return <ErrorNotice message={errorMessage(query.error)} />;
  const { money, time, money_withheld: withheld } = query.data;
  if (!money && !time && !withheld) {
    return (
      <EmptyNotice
        text="Dit onderdeel is er voor jou niet"
        supportingText="De investeerruimte gaat over de hele organisatie."
      />
    );
  }
  return (
    <ReportBlock bare={bare} testId="investment" title="Investeerruimte">
      <div className="grip-invest">
        {money && (
          <nldd-container gap="8">
            <MoneyDerivation money={money} year={query.data.year} />
            <Quiet>
              Wat geteld is: de verwachte omzet van externe opdrachten met akkoord (ook mondeling),
              min wat de mensen volgens hun target moeten binnenbrengen, min ongedekte kosten, min
              wat interne opdrachten volgens hun begroting gebruiken. Voorlopige definitie.
            </Quiet>
          </nldd-container>
        )}
        {withheld && (
          <nldd-inline-dialog
            data-testid="investment-withheld"
            text="De investeerruimte in geld is niet te tonen"
            supporting-text={`Minder dan ${withheld.min_persons} mensen hebben een target. Het bedrag zou dan het target van een persoon verraden.`}
          />
        )}
        {time && <TimeReading time={time} />}
      </div>
      {money && (money.unpriced_assignments ?? []).length > 0 && (
        <nldd-banner
          variant="warning"
          size="sm"
          text={`Niet meegeteld, omdat de bedragen niet te berekenen zijn: ${money.unpriced_assignments.join(', ')}.`}
        />
      )}
      {money && <MoneyMonths money={money} year={query.data.year} />}
    </ReportBlock>
  );
}
