import type { KeyFigures as Figures } from '@/features/assignments/financeApi';
import { formatEuro } from '@/lib/format';
import { KeyFigures } from '@/ui/layout';

/** Where delivery and invoicing stand, over the whole assignment. */
export function BillingFigures({ figures }: { figures: Figures }) {
  const money = (cents: number | null) => (cents === null ? 'Niet bekend' : formatEuro(cents));
  const shown = [
    {
      label: 'Aangeleverd',
      value: formatEuro(figures.delivered_cents),
      cents: figures.delivered_cents,
    },
    {
      label: 'Nog aan te leveren',
      value: money(figures.to_deliver_cents),
      cents: figures.to_deliver_cents,
    },
    {
      label: 'Gefactureerd',
      value: formatEuro(figures.invoiced_cents),
      cents: figures.invoiced_cents,
    },
    {
      label: 'Nog te factureren',
      value: formatEuro(figures.to_invoice_cents),
      cents: figures.to_invoice_cents,
      ...(figures.to_invoice_cents < 0
        ? { detail: 'Meer gefactureerd dan aangeleverd', critical: true }
        : {}),
    },
  ]
    .filter((figure) => figure.cents !== 0)
    .map(({ cents: _cents, ...figure }) => figure);
  if (shown.length === 0) return null;
  return <KeyFigures label="Aanleveren en factureren" figures={shown} />;
}
