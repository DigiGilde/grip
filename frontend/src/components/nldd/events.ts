/**
 * Binding helpers between React and the nldd-* custom elements.
 *
 * 1. Custom events are not React events. Several nldd events are dispatched
 *    with `bubbles: false`, which React's delegated listeners never see, so an
 *    `on*` JSX prop silently never fires. Always listen on the element itself.
 * 2. Booleans must be `true | undefined`, never `false`: React can write
 *    `false` as the attribute "false", and the element reads presence as true.
 */
import { useEffect, useRef, type RefObject } from 'react';

/** Pass booleans for nldd-* attributes through here. */
export function orUndef(value: boolean | undefined): true | undefined {
  return value ? true : undefined;
}

/**
 * Subscribe to an event on a custom element. Listens on the element itself, so
 * it works for non-bubbling events too.
 *
 * The effect has no dependency list on purpose: a ref assignment does not
 * cause a render, so an element that mounts later (behind a loading state)
 * would never get its listener from an effect keyed on the ref object. The
 * check after each commit is a comparison and only touches the DOM when the
 * element changed.
 */
export function useNlddEvent<T extends HTMLElement = HTMLElement>(
  ref: RefObject<T | null>,
  type: string,
  handler: ((event: Event) => void) | undefined,
): void {
  const saved = useRef(handler);
  const attached = useRef<{ el: T; type: string; listener: (event: Event) => void } | null>(null);
  const hasHandler = handler !== undefined;

  useEffect(() => {
    saved.current = handler;
    const el = hasHandler ? ref.current : null;
    const current = attached.current;
    if (current && (current.el !== el || current.type !== type)) {
      current.el.removeEventListener(current.type, current.listener);
      attached.current = null;
    }
    if (el && !attached.current) {
      const listener = (event: Event) => saved.current?.(event);
      el.addEventListener(type, listener);
      attached.current = { el, type, listener };
    }
  });

  useEffect(
    () => () => {
      const current = attached.current;
      if (current) current.el.removeEventListener(current.type, current.listener);
      attached.current = null;
    },
    [],
  );
}
