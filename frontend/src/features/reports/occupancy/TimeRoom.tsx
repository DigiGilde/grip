import { formatFte } from '@/lib/format';
import { Quiet } from '@/ui/layout';
import type { InvestmentTime } from '../api';
import { monthName } from '../labels';
import { MoneyCell, NumberCell } from '../ui';

const count = (number: number, one: string, many: string) =>
  `${number} ${number === 1 ? one : many}`;

/** Investeerruimte in tijd: free capacity per month, in FTE and, for who may see rates, in money. */
export function TimeRoom({ time }: { time: InvestmentTime }) {
  const months = time.months ?? [];
  const valued = 'value_cents' in time;
  const unvalued = months.reduce((most, month) => Math.max(most, month.unvalued_count ?? 0), 0);
  return (
    <nldd-container gap="8" data-testid="investment-time">
      <nldd-title size="display-5" text="Investeerruimte in tijd" heading-level={2} />
      <nldd-table
        accessible-label="Vrije capaciteit in de komende maanden"
        columns={`minmax(130px,1fr) 100px${valued ? ' 150px' : ''}`}
        sm-columns={`minmax(0,1fr) 80px${valued ? ' 110px' : ''}`}
      >
        <nldd-table-row slot="header">
          <nldd-text-cell text="Maand" />
          <nldd-text-cell text="Vrij (FTE)" horizontal-alignment="right" />
          {valued && <nldd-text-cell text="Tegen inzettarief" horizontal-alignment="right" />}
        </nldd-table-row>
        {months.map((month) => (
          <nldd-table-row key={month.month}>
            <nldd-text-cell text={monthName(month.month)} />
            <NumberCell text={formatFte(month.free_fte)} />
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
