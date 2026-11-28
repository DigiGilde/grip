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

/**
 * `select` on an nldd-menu-item whose choice opens a sheet or a dialog, in the
 * popup menu of a button or icon button. Since 0.24.0 a chosen item blinks
 * before its menu closes. A sheet that opens during the blink remembers the
 * item as where focus goes back to; by the time the sheet closes the menu is
 * gone, and focus falls to the page. Acting once the menu has closed lets
 * focus return to the button that opened the menu. The overflow menu of a
 * toolbar gives focus back itself since 0.26.2, so its items need none of this.
 */
export function useMenuSelect<T extends HTMLElement = HTMLElement>(
  ref: RefObject<T | null>,
  handler: (() => void) | undefined,
): void {
  useNlddEvent(ref, 'select', handler ? (event) => afterMenuCloses(event, handler) : undefined);
}

/** Runs `action` once the menu that `event` passed through has closed. */
export function afterMenuCloses(event: Event, action: () => void): void {
  const menu = event
    .composedPath()
    .find((node): node is Element => node instanceof Element && node.localName === 'nldd-menu');
  if (!menu?.matches(':popover-open')) {
    action();
    return;
  }
  let done = false;
  const run = () => {
    if (done) return;
    done = true;
    clearTimeout(fallback);
    action();
  };
  // A menu that leaves the page while it blinks never says it closed.
  const fallback = setTimeout(run, 1000);
  menu.addEventListener('toggle', run, { once: true });
}
