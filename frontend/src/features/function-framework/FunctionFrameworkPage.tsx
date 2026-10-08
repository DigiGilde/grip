import { useInstance } from '@/layout/useInstance';
import { Page } from '@/ui/layout';
import { FunctionFrameworkSection } from './FunctionFrameworkSection';

/**
 * The function groups of the Functiegebouw Rijk and their scales, on a page
 * of its own: a reference list of some sixty groups does not belong under
 * the form and model settings.
 */
export function FunctionFrameworkPage() {
  const instance = useInstance();
  return (
    <Page
      title="Functiegebouw Rijk"
      lead="De functiegroepen met hun schalen, waaruit je kiest bij een vacature."
      instanceName={instance?.name}
    >
      <FunctionFrameworkSection />
    </Page>
  );
}
