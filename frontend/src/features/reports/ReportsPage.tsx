import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { EmptyNotice, LoadError, Loading } from '@/ui/layout';
import { RouterLinks } from '@/layout/RouterLinks';
import { useInstance } from '@/layout/useInstance';
import { PageHeading } from '@/pages/PageHeading';
import { ActionBar } from '@/ui/ActionBar';
import { fetchInvestment, fetchSteering, reportKeys } from './api';
import { landingTiles, type Tile } from './tiles';
import { TOPICS, topicPath } from './topics';
import './ui';
import { useReportYear } from './useReportYear';
import { reportYearOptions } from './years';

/** One headline figure, and the way into the view that explains it. */
function TileLink({ tile, year }: { tile: Tile; year: string }) {
  return (
    <Link
      to={topicPath(tile.topic, year)}
      className={tile.attention ? 'grip-tile grip-tile--attention' : 'grip-tile'}
      data-testid={`tile-${tile.topic}`}
    >
      <span className="grip-tile__topic">{TOPICS[tile.topic].title}</span>
      <span className="grip-tile__label">{tile.label}</span>
      <span className="grip-tile__value">{tile.value}</span>
      <span className="grip-tile__context">{tile.context}</span>
      {tile.attention && (
        <span className="grip-tile__flag">
          <span className="grip-mark" aria-hidden="true">
            !
          </span>
          {tile.attention}
        </span>
      )}
    </Link>
  );
}

/**
 * Rapportage: the handful of figures to check each week, on one screen.
 * Every tile opens the view of its topic; nothing else is here but the year.
 */
export function ReportsPage() {
  const instance = useInstance();
  const [year, setYear] = useReportYear();
  const query = useQuery({
    queryKey: reportKeys.steering(year),
    queryFn: () => fetchSteering(year),
  });
  // Its own request, so a problem with it never hides the other figures.
  const investment = useQuery({
    queryKey: reportKeys.investment(year),
    queryFn: () => fetchInvestment(year),
  });
  const tiles = query.data ? landingTiles(query.data, investment.data) : [];

  return (
    <nldd-simple-section>
      <PageHeading text="Rapportage" instanceName={instance?.name} />
      <nldd-container gap="16">
        <RouterLinks>
          <ActionBar
            label="Rapportage filteren"
            filters={[
              {
                label: 'Jaar',
                value: year,
                onChange: setYear,
                options: reportYearOptions(),
                width: '140px',
              },
            ]}
            actions={[{ text: 'Jaarverantwoording', href: topicPath('jaarverantwoording', year) }]}
          />
        </RouterLinks>
        {query.isPending && <Loading />}
        {query.isError && <LoadError error={query.error} retry={() => void query.refetch()} />}
        {query.isSuccess && tiles.length === 0 && (
          <EmptyNotice
            text="Er is voor jou geen sturingsinformatie"
            supportingText="Je ziet hier de cijfers van opdrachten die je beheert en van personen aan wie je leiding geeft."
          />
        )}
        {tiles.length > 0 && (
          <ul className="grip-tiles" aria-label={`Kerncijfers ${year}`}>
            {tiles.map((tile) => (
              <li key={tile.topic}>
                <TileLink tile={tile} year={year} />
              </li>
            ))}
          </ul>
        )}
      </nldd-container>
    </nldd-simple-section>
  );
}
