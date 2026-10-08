/** The one-line answers a node card gives, as text. */
import type { NodeLookup, NodePath, PathStep } from './api';
import { uriHost } from './labels';

/**
 * "Where does this come from?": the political input at the end of the
 * chain by title, the others counted, and how many steps away the nearest
 * one is. A node that falls under another linked node says that instead,
 * so the same chain is not told twice. Empty when there is nothing to say.
 */
export function originLine(item: NodeLookup): string {
  if (item.falls_under) return `Valt onder: ${item.falls_under.title}`;
  const origins = item.origins ?? [];
  const first = origins[0];
  if (!first) {
    if (item.node?.type === 'politieke_input') return 'Dit is een politieke input';
    const elsewhere = (item.paths ?? []).some((path) => endOf(path)?.external);
    return elsewhere ? 'Loopt door in een ander corpus' : '';
  }
  const others = origins.length - 1;
  const more = others === 0 ? '' : others === 1 ? ', en 1 andere' : `, en ${others} andere`;
  return `Komt voort uit: ${first.title}${more}`;
}

/** How far the nearest political input is, for the detail and the card label. */
export function stepsText(item: NodeLookup): string {
  const steps = item.steps_to_origin;
  if (item.falls_under || steps === null || steps === undefined || steps <= 0) return '';
  return steps === 1 ? '1 stap' : `${steps} stappen`;
}

export function endOf(path: NodePath): PathStep | undefined {
  const steps = path.steps ?? [];
  return steps[steps.length - 1];
}

/** The corpus a step in another corpus lies in: its name when known, else its host. */
export function corpusLabel(step: { uri: string; corpus_name?: string | null }): string {
  return step.corpus_name || uriHost(step.uri) || 'een ander corpus';
}

/** Whether a status is worth a tag: the usual one is not. */
export function notableStatus(status: string | null | undefined): string {
  return status && status.toLowerCase() !== 'actief' ? status : '';
}
