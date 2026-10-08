import { useInstance } from '@/layout/useInstance';
import { PageHeading } from './PageHeading';

/** A screen that has a place in the navigation but is not built yet. */
export function PlaceholderPage({ title }: { title: string }) {
  const instance = useInstance();
  return (
    <nldd-simple-section>
      <PageHeading text={title} instanceName={instance?.name} />
      <nldd-inline-dialog
        text="Dit scherm is nog niet beschikbaar"
        supporting-text="Dit onderdeel wordt nog gebouwd."
      />
    </nldd-simple-section>
  );
}
