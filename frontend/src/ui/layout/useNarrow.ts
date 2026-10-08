import { useEffect, useState } from 'react';

/** The design system's narrow breakpoint: a phone held upright. */
const NARROW = '(max-width: 640px)';

/**
 * True on a narrow screen. For the few places where the narrow layout is a
 * different structure and not only a different size; follows the window.
 * Without a window that can be asked (a test), it is the wide layout.
 */
export function useNarrow(query: string = NARROW): boolean {
  const [narrow, setNarrow] = useState(
    () => typeof window !== 'undefined' && !!window.matchMedia && window.matchMedia(query).matches,
  );
  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return;
    const media = window.matchMedia(query);
    const onChange = () => setNarrow(media.matches);
    onChange();
    media.addEventListener('change', onChange);
    return () => media.removeEventListener('change', onChange);
  }, [query]);
  return narrow;
}
