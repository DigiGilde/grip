/** How a message that does not arrive is told on Beheer > Koppelingen. Pure, so it is tested. */
import { formatDateTime } from '@/features/quotes/format';
import type { UndeliveredMessage } from './api';

/** Why the message does not arrive, since when, and what grip does about it. */
export function standing(message: UndeliveredMessage): string {
  const since = `${message.reason}. Sinds ${formatDateTime(message.since)}`;
  if (message.final) return `${since}. Komt niet meer vanzelf aan.`;
  if (message.retry_until) {
    return `${since}. Grip probeert het tot ${formatDateTime(message.retry_until)}.`;
  }
  return `${since}. Wordt opnieuw verstuurd.`;
}
