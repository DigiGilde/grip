/**
 * The paths of a node as a small tree: what all paths share is told once
 * (the trunk), and each end point gets the rest of its own way (a branch).
 */
import type { NodePath, PathStep } from './api';

export interface PathBranch {
  /** The relation between the last shared step and the first step of this branch. */
  lead: string | null;
  steps: PathStep[];
}

export interface PathTree {
  /** The steps every path starts with, from the node itself. */
  trunk: PathStep[];
  /** One per end point; empty when there is one path, which is then all trunk. */
  branches: PathBranch[];
}

export function toTree(paths: readonly NodePath[]): PathTree {
  const all = paths.map((path) => path.steps ?? []).filter((steps) => steps.length > 0);
  const first = all[0];
  if (!first) return { trunk: [], branches: [] };
  if (all.length === 1) return { trunk: first, branches: [] };

  let shared = 0;
  while (all.every((steps) => steps[shared] && steps[shared]?.uri === first[shared]?.uri)) {
    shared += 1;
  }
  // Every path starts at the node itself, so at least that step is shared.
  shared = Math.max(1, shared);
  const trunk = first.slice(0, shared).map((step, index) =>
    // Where the paths part, the relation belongs to each branch.
    index === shared - 1 ? { ...step, edge_type: null } : step,
  );
  const branches = all
    .map((steps) => ({ lead: steps[shared - 1]?.edge_type ?? null, steps: steps.slice(shared) }))
    .filter((branch) => branch.steps.length > 0);
  return { trunk, branches };
}
