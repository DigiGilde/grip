import { useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { errorMessage } from '@/api/client';
import { EmptyNotice, ErrorNotice, Loading } from '@/ui/layout';
import { RouterLinks } from '@/layout/RouterLinks';
import { useInstance } from '@/layout/useInstance';
import { PageHeading } from '@/pages/PageHeading';
import { ActionBar } from '@/ui/ActionBar';
import { fetchSteering, reportKeys, type Steering } from './api';
import { InvestmentView } from './InvestmentView';
import { OccupancyBlock } from './occupancy/OccupancyBlock';
import {
  BillabilityBlock,
  CostsBlock,
  OpenRolesBlock,
  PipelineBlock,
  TurnoverBlock,
} from './SteeringView';
import { TOPICS, isTopic, reportsPath, type TopicSlug } from './topics';
import { useReportYear } from './useReportYear';
import { YearAccountView } from './YearAccountView';
import { reportYearOptions } from './years';

/** The block of a topic, or null when the API sent none for this reader. */
function topicBlock(slug: TopicSlug, steering: Steering) {
  const year = steering.year;
  switch (slug) {
    case 'omzet':
      return steering.turnover && <TurnoverBlock bare turnover={steering.turnover} year={year} />;
    case 'bezetting':
      return (
        steering.occupancy && <OccupancyBlock bare occupancy={steering.occupancy} year={year} />
      );
    case 'pijplijn':
      return steering.pipeline && <PipelineBlock bare pipeline={steering.pipeline} year={year} />;
    case 'kosten':
      return steering.costs && <CostsBlock bare costs={steering.costs} year={year} />;
    case 'declarabiliteit':
      return (
        steering.billability && (
          <BillabilityBlock bare billability={steering.billability} year={year} />
        )
      );
    case 'open-rollen':
      return steering.open_roles && <OpenRolesBlock bare openRoles={steering.open_roles} />;
    default:
      return null;
  }
}

function SteeringTopic({ slug, year }: { slug: TopicSlug; year: string }) {
  const query = useQuery({ queryKey: reportKeys.steering(year), queryFn: () => fetchSteering(year) });
  if (query.isPending) return <Loading />;
  if (query.isError) return <ErrorNotice message={errorMessage(query.error)} />;
  return (
    topicBlock(slug, query.data) || (
      <EmptyNotice
        text="Dit onderdeel is er voor jou niet"
        supportingText="Je ziet hier alleen cijfers van opdrachten en personen waar je bij betrokken bent."
      />
    )
  );
}

/**
 * One topic of Rapportage on its own page: the answer on top, the table
 * below. The year travels along in the address, and so does the way back.
 */
export function ReportTopicPage() {
  const { topic } = useParams();
  const instance = useInstance();
  const [year, setYear] = useReportYear();
  const known = isTopic(topic);

  return (
    <nldd-simple-section>
      <PageHeading text={known ? TOPICS[topic].title : 'Rapportage'} instanceName={instance?.name} />
      <nldd-container gap="16">
        <RouterLinks>
          <nldd-link href={reportsPath(year)} text="Terug naar Rapportage" size="md" />
        </RouterLinks>
        {known ? (
          <>
            <ActionBar
              label={`${TOPICS[topic].title} filteren`}
              filters={[
                {
                  label: 'Jaar',
                  value: year,
                  onChange: setYear,
                  options: reportYearOptions(),
                  width: '140px',
                },
              ]}
            />
            {topic === 'investeerruimte' ? (
              <InvestmentView bare year={year} />
            ) : topic === 'jaarverantwoording' ? (
              <YearAccountView bare year={year} />
            ) : (
              <SteeringTopic slug={topic} year={year} />
            )}
          </>
        ) : (
          <EmptyNotice
            text="Deze rapportage bestaat niet"
            supportingText="Ga terug naar Rapportage en kies een onderdeel."
          />
        )}
      </nldd-container>
    </nldd-simple-section>
  );
}
