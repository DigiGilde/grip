/**
 * What a screen shows instead of content: one shape for every reason.
 *
 * A page or a part of a page is in exactly one of these states: loading, the
 * content, nothing to show, no access, not found, or not reachable. No screen
 * writes its own version of the last four; they render these. Each carries a
 * `data-state` so a sweep over all routes can tell them apart (see
 * `just check-access`).
 */
import type { ReactNode } from 'react';
import { loadFailure, type LoadFailure } from '@/api/client';
import { Button } from '@/ui/Button';

export type ScreenState = LoadFailure | 'empty';

interface StateAction {
  text: string;
  onClick?: () => void;
  href?: string;
}

interface StateNoticeProps {
  state: ScreenState;
  /** What is the case, in one short sentence. */
  text: string;
  /** Who can change it, or what the reader can do. */
  detail?: ReactNode;
  action?: StateAction;
}

/** Left-aligned under the page's title, like the content it stands in for. */
export function StateNotice({ state, text, detail, action }: StateNoticeProps) {
  return (
    <div data-state={state} role={state === 'empty' ? undefined : 'status'}>
      <nldd-container gap="8">
        <nldd-text>{text}</nldd-text>
        {detail ? (
          <nldd-text size="sm" color="secondary">
            {detail}
          </nldd-text>
        ) : null}
        {action ? (
          <nldd-container layout="row" gap="8">
            <Button
              text={action.text}
              {...(action.onClick ? { onClick: action.onClick } : {})}
              {...(action.href ? { href: action.href } : {})}
            />
          </nldd-container>
        ) : null}
      </nldd-container>
    </div>
  );
}

interface NoAccessProps {
  /** For whom this is, as a full sentence: "Dit is voor beheerders." */
  who?: string;
  /** Where the reader can go instead. */
  back?: { text: string; href: string };
}

/** The reader may not see this. Says for whom it is, never what it holds. */
export function NoAccess({ who, back }: NoAccessProps) {
  return (
    <StateNotice
      state="no-access"
      text="Je hebt hier geen toegang"
      detail={who ?? 'Vraag de beheerder of de eigenaar om toegang.'}
      {...(back ? { action: back } : {})}
    />
  );
}

/** Not there, or not for this reader: the server does not say which, nor do we. */
export function NotFound({ what = 'Dit', back }: { what?: string; back?: NoAccessProps['back'] }) {
  return (
    <StateNotice
      state="not-found"
      text={`${what} is niet gevonden`}
      detail="Het bestaat niet, of je hebt er geen toegang toe."
      {...(back ? { action: back } : {})}
    />
  );
}

interface LoadErrorProps {
  /** What the request threw. */
  error: unknown;
  /** Ask again; offered only when asking again can help. */
  retry?: () => void;
  /** For whom this is, when the reader has no access. */
  who?: string;
  /** What was asked for, when it is not found: "Deze opdracht". */
  what?: string;
  back?: NoAccessProps['back'];
}

/**
 * A request for data that gave nothing to show. Every query's error goes
 * through here, so no access, not found and not reachable look and read the
 * same on every screen.
 */
export function LoadError({ error, retry, who, what, back }: LoadErrorProps) {
  const failure = loadFailure(error);
  if (failure === 'no-access') return <NoAccess who={who} back={back} />;
  if (failure === 'not-found') return <NotFound what={what} back={back} />;
  return (
    <StateNotice
      state={failure}
      text={failure === 'unreachable' ? 'Grip is niet bereikbaar' : 'Dit laden is niet gelukt'}
      detail={
        failure === 'unreachable'
          ? 'Controleer je verbinding en probeer het opnieuw.'
          : 'Probeer het opnieuw. Blijft het zo, meld het dan aan de beheerder.'
      }
      {...(retry ? { action: { text: 'Probeer opnieuw', onClick: retry } } : {})}
    />
  );
}
