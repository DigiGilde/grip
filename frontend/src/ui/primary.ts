/**
 * One filled accent per page: the next step.
 *
 * When the head of an open thing already carries the next step as its
 * primary button, the page below it must not show a second one. The head
 * says so here; the shared button and action bar then draw their "primary"
 * as an ordinary action. A screen never has to know.
 */
import { createContext, useContext } from 'react';

export const PrimaryTakenContext = createContext(false);

/** True when the one accent of the page is already in use above this point. */
export function usePrimaryTaken(): boolean {
  return useContext(PrimaryTakenContext);
}
