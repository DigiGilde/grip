/** The fields of the factuurinformatie, as one sheet asks them. */
import { TextInput } from '@/features/assignments/ui';
import type { BillingDetails, DetailKey } from './billingApi';
import { ADDRESS_KEYS, CONTACT_KEYS, REQUIRED_DETAILS } from './billingDetails';
import { DETAIL_LABELS } from './periodText';

export function DetailFields({
  keys,
  details,
  onChange,
  required = true,
}: {
  keys: DetailKey[];
  details: BillingDetails;
  onChange: (key: DetailKey, value: string) => void;
  /** Whether the address must be complete; otherwise every field is optional. */
  required?: boolean;
}) {
  return (
    <>
      {keys.map((key) => (
        <TextInput
          key={key}
          label={DETAIL_LABELS[key]}
          value={details[key] ?? ''}
          onChange={(value) => onChange(key, value)}
          {...(required && REQUIRED_DETAILS.includes(key)
            ? { required: true }
            : { optional: true })}
          {...(key === 'reference'
            ? { hint: 'Een verplichtingennummer of ordernummer van de opdrachtgever' }
            : {})}
        />
      ))}
    </>
  );
}

/** The address and the contact at the financial department, under their two headings. */
export function BillingDetailsFields({
  details,
  onChange,
  required = true,
}: {
  details: BillingDetails;
  onChange: (details: BillingDetails) => void;
  required?: boolean;
}) {
  const change = (key: DetailKey, value: string) => onChange({ ...details, [key]: value });
  return (
    <>
      <nldd-title size={5} heading-level={2} text="Waar gaat de factuur heen?" />
      <DetailFields keys={ADDRESS_KEYS} details={details} onChange={change} required={required} />
      <nldd-title size={5} heading-level={2} text="Contact bij de financiële afdeling" />
      <DetailFields keys={CONTACT_KEYS} details={details} onChange={change} required={required} />
    </>
  );
}
