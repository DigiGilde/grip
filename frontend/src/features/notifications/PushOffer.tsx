import { Button } from '@/features/assignments/ui';
import { PATHS } from '@/paths';
import { ErrorNotice, Quiet } from '@/ui/layout';
import { usePush } from './usePush';

/**
 * The offer to be notified, for a page where it fits: the task list. Shows
 * nothing unless notifications can be switched on here and are not on yet.
 * Pressing the button is what makes the browser ask.
 */
export function PushOffer() {
  const { query, state, busy, error, on } = usePush();
  if (!query.data?.available || state !== 'off') return null;
  return (
    <nldd-container layout="row" gap="16" vertical-alignment="center">
      <Quiet>
        Wil je een melding als er een taak op je wacht? Hooguit {query.data.daily_cap} per dag,
        zonder namen of bedragen.
      </Quiet>
      <Button text="Zet meldingen aan" onClick={() => void on()} loading={busy} />
      <nldd-link href={PATHS.notifications} text="Instellen" size="md" />
      {error ? <ErrorNotice message={error} /> : null}
    </nldd-container>
  );
}
