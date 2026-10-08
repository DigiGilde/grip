/** Dutch wording for the codes of the client-side endpoints. */
import type { BadgeColor } from '@/features/assignments/labels';
import type { Delivery } from './api';

const DELIVERY_SUBJECT: Record<string, string> = {
  sendAssignmentRequest: 'De aanvraag',
  sendAcceptance: 'Het akkoord',
  sendRejection: 'De afwijzing',
};

/** Whether the other side has the message, in a sentence. */
export function deliveryText(delivery: Delivery | null | undefined): string {
  if (!delivery) return 'Niet verstuurd';
  const subject = DELIVERY_SUBJECT[delivery.operation] ?? 'Het bericht';
  switch (delivery.status) {
    case 'sent':
      return `${subject} is aangekomen bij de opdrachtnemer`;
    case 'pending':
      return `${subject} wacht op verzending`;
    case 'rejected':
      return `${subject} is geweigerd door de opdrachtnemer`;
    case 'dead':
      return `${subject} is niet aangekomen`;
    default:
      return `${subject}: ${delivery.status}`;
  }
}

export const DELIVERY_SHORT: Record<string, string> = {
  sent: 'Aangekomen',
  pending: 'Wacht op verzending',
  rejected: 'Geweigerd',
  dead: 'Niet aangekomen',
};

export const DELIVERY_COLORS: Record<string, BadgeColor> = {
  sent: 'success',
  pending: 'neutral',
  rejected: 'critical',
  dead: 'critical',
};

export const MILESTONE_STATE_LABELS: Record<string, string> = {
  planned: 'Gepland',
  in_progress: 'Bezig',
  done: 'Klaar',
  cancelled: 'Vervallen',
};
