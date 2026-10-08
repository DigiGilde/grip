import type { BrowserState } from './api';

/** Why notifications cannot be switched on here, in a sentence; null when they can. */
export function blockedText(state: BrowserState | null): string | null {
  switch (state) {
    case 'unsupported':
      return 'Deze browser kan geen meldingen tonen.';
    case 'needs-install':
      return 'Op een iPhone of iPad werken meldingen alleen vanaf het beginscherm. Kies in Safari Deel en dan Zet op beginscherm, en open grip daar.';
    case 'no-worker':
      return 'Meldingen werken niet in deze ontwikkelomgeving.';
    case 'denied':
      return 'Je hebt meldingen van grip in deze browser geblokkeerd. Sta ze toe bij de instellingen van de site, naast het adres.';
    default:
      return null;
  }
}
