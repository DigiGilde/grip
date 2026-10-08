import { useEffect, useState, type RefObject } from 'react';

/**
 * The message of a form after a failed submit, until the reader answers it.
 *
 * A message is about the form as it was sent. Once the reader changes a field
 * it has been answered and goes, so no "fill in a name" stands next to a name
 * that is there by now. The next submit shows it again if it still applies.
 * Listens in the capture phase on the element that holds the fields: the
 * design system's fields report a change on themselves, and not every one of
 * those events bubbles.
 */
export function useFormMessage(
  holder: RefObject<HTMLElement | null>,
  error: string | null | undefined,
): { shown: string | null; submitted: () => void } {
  const [answered, setAnswered] = useState<string | null>(null);
  useEffect(() => {
    const element = holder.current;
    if (!element) return;
    const changed = () => setAnswered(error ?? null);
    element.addEventListener('input', changed, true);
    element.addEventListener('change', changed, true);
    return () => {
      element.removeEventListener('input', changed, true);
      element.removeEventListener('change', changed, true);
    };
  }, [holder, error]);
  return {
    shown: error && error !== answered ? error : null,
    submitted: () => setAnswered(null),
  };
}
