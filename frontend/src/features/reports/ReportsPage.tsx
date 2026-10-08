import { useState } from 'react';
import { InlineSelect } from '@/features/assignments/ui';
import { Segments } from '@/features/team/ui/controls';
import { useInstance } from '@/layout/useInstance';
import { PageHeading } from '@/pages/PageHeading';
import { SteeringView } from './SteeringView';
import { YearAccountView } from './YearAccountView';
import { currentReportYear, reportYearOptions } from './years';

type View = 'steering' | 'year-account';

/**
 * Rapportage: the steering overview and the year account of a budget year.
 * The year filter sits above both and scopes everything below it. The report
 * of one assignment is reached from the year account.
 */
export function ReportsPage() {
  const instance = useInstance();
  const [view, setView] = useState<View>('steering');
  const [year, setYear] = useState(currentReportYear);
  return (
    <nldd-simple-section>
      <PageHeading text="Rapportage" instanceName={instance?.name} />
      <nldd-container gap="16">
        <nldd-container layout="wrap" gap="12" vertical-alignment="center">
          <InlineSelect
            label="Jaar"
            value={year}
            onChange={setYear}
            options={reportYearOptions()}
            width="140px"
          />
          <Segments
            label="Weergave"
            value={view}
            onChange={(next) => setView(next === 'year-account' ? 'year-account' : 'steering')}
            options={[
              { value: 'steering', label: 'Sturing' },
              { value: 'year-account', label: 'Jaarverantwoording' },
            ]}
          />
        </nldd-container>
        {view === 'steering' ? <SteeringView year={year} /> : <YearAccountView year={year} />}
      </nldd-container>
    </nldd-simple-section>
  );
}
