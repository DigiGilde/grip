import type { SectionAction } from './section';

/** The action that closes fields that were opened from a section. */
export function cancelAction(onClick: () => void): SectionAction {
  return { text: 'Annuleer', onClick, appearance: 'neutral-transparent' };
}
