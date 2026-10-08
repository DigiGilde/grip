/**
 * The buttons of grip: three ranks and nothing else.
 *
 *   primary     the one next step of a page or a state; the only accent
 *   secondary   every other action: a real button shape, neutral
 *   destructive what cannot be undone, in a dialog or a sheet that asks first
 *
 * An action always looks like a button. Bare text that does something reads
 * as a label next to a boxed button, so there is no "text" rank to choose.
 * `QuietButton` is the exception with a fixed list of places: the way out of a
 * sheet or dialog ("Annuleer"), and a small action inside a line of a
 * conversation (answer a remark). Going somewhere is a link, never a button,
 * unless going there is the page's primary step. See docs/ontwerp.md.
 */
import { useRef } from 'react';
import { orUndef, useNlddEvent } from '@/components/nldd/events';
import { usePrimaryTaken } from './primary';

export type ButtonRank = 'primary' | 'secondary' | 'destructive';

export interface ButtonProps {
  text: string;
  onClick?: () => void;
  /** Default secondary. One primary per page or state. */
  appearance?: ButtonRank;
  size?: 'xs' | 'sm' | 'md';
  type?: 'button' | 'submit';
  loading?: boolean;
  /** Not possible now. Say why next to the button. */
  disabled?: boolean;
  accessibleLabel?: string;
  slot?: string;
  /** For a button that is a link: the page's primary step leads elsewhere. */
  href?: string;
}

function Base({
  text,
  onClick,
  appearance,
  size,
  type,
  loading,
  disabled,
  accessibleLabel,
  slot,
  href,
}: Omit<ButtonProps, 'appearance'> & { appearance: ButtonRank | 'neutral-transparent' }) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'click', onClick ? () => onClick() : undefined);
  return (
    <nldd-button
      ref={ref}
      text={text}
      appearance={appearance}
      {...(size ? { size } : {})}
      {...(type ? { type } : {})}
      {...(slot ? { slot } : {})}
      {...(href ? { href } : {})}
      {...(accessibleLabel ? { 'accessible-label': accessibleLabel } : {})}
      loading={orUndef(loading)}
      disabled={orUndef(disabled)}
    />
  );
}

/** An action. Secondary unless it is the one next step. */
export function Button({ appearance = 'secondary', ...rest }: ButtonProps) {
  // The head of the page already shows the next step: this one steps back.
  const taken = usePrimaryTaken();
  return <Base appearance={appearance === 'primary' && taken ? 'secondary' : appearance} {...rest} />;
}

/**
 * The quiet way out or a small action inside a line: "Annuleer" in a sheet,
 * "Antwoord" under a remark. Not for an action that stands beside a button.
 */
export function QuietButton(props: Omit<ButtonProps, 'appearance'>) {
  return <Base appearance="neutral-transparent" {...props} />;
}
