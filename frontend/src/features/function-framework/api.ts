/** The Functiegebouw Rijk: function families, groups and their scales. */
import { apiGet, apiPatch, apiPost } from '@/api/client';
import type { RequestHeaders } from '@/api/client';

export interface FunctionGroup {
  id: string;
  version?: number;
  family_id: string;
  name: string;
  scales: number[];
  /** "schaal 11 t/m 13" */
  scales_text: string;
  source: 'reference' | 'manual';
  source_url?: string | null;
  valid_to?: string | null;
  edited: boolean;
}

export interface FunctionFamily {
  id: string;
  name: string;
  source: 'reference' | 'manual';
  source_url?: string | null;
  valid_to?: string | null;
  groups: FunctionGroup[];
}

export interface FunctionFramework {
  source: {
    name: string;
    source_url: string;
    read_on: string;
    reference_families: number;
    reference_groups: number;
  };
  families: FunctionFamily[];
  can_manage: boolean;
}

export interface ReloadResult {
  families_created: number;
  families_updated: number;
  groups_created: number;
  groups_updated: number;
  groups_kept: number;
}

export interface FunctionGroupInput {
  family_id: string;
  name: string;
  scales: number[];
  valid_to?: string | null;
}

const BASE = '/api/function-framework';

export const FRAMEWORK_KEYS = {
  /** What a vacancy chooses from: valid today. */
  current: ['function-framework', 'current'] as const,
  /** Everything, ended entries included, for beheer. */
  all: ['function-framework', 'all'] as const,
};

export const fetchFunctionFramework = (includeEnded = false) =>
  apiGet<FunctionFramework>(BASE, { include_ended: includeEnded || undefined });
export const reloadFunctionFramework = () => apiPost<ReloadResult>(`${BASE}/reload`);
export const createFunctionGroup = (input: FunctionGroupInput) =>
  apiPost<FunctionGroup>(`${BASE}/groups`, input);
export const updateFunctionGroup = (
  id: string,
  input: Partial<FunctionGroupInput>,
  headers?: RequestHeaders,
) => apiPatch<FunctionGroup>(`${BASE}/groups/${id}`, input, headers);
export const createFunctionFamily = (name: string) =>
  apiPost<FunctionFamily>(`${BASE}/families`, { name });

/** A group with the name of its family, as a picker shows it. */
export interface GroupChoice extends FunctionGroup {
  family_name: string;
}

export function groupChoices(framework: FunctionFramework | undefined): GroupChoice[] {
  return (framework?.families ?? []).flatMap((family) =>
    family.groups.map((group) => ({ ...group, family_name: family.name })),
  );
}

/** Groups whose name or family name contains every word of the query. */
export function searchGroups(choices: GroupChoice[], query: string): GroupChoice[] {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  if (words.length === 0) return choices;
  return choices.filter((choice) => {
    const text = `${choice.name} ${choice.family_name}`.toLowerCase();
    return words.every((word) => text.includes(word));
  });
}

/** Suggested groups first (their scales overlap the given ones), the rest after. */
export function suggestedFirst(choices: GroupChoice[], scales: number[] | null | undefined) {
  if (!scales || scales.length === 0) return { suggested: [], others: choices };
  const wanted = new Set(scales);
  const suggested = choices.filter((choice) => choice.scales.some((scale) => wanted.has(scale)));
  const others = choices.filter((choice) => !suggested.includes(choice));
  return { suggested, others };
}

/** "11, 12, 13" or "11-13" as scale numbers; null when it cannot be read. */
export function parseScales(input: string): number[] | null {
  const scales = new Set<number>();
  for (const part of input.split(/[,;\s]+/).filter(Boolean)) {
    const range = /^(\d{1,2})\s*(?:-|t\/m)\s*(\d{1,2})$/.exec(part);
    if (range) {
      const from = Number(range[1]);
      const to = Number(range[2]);
      if (from > to) return null;
      for (let scale = from; scale <= to; scale += 1) scales.add(scale);
    } else if (/^\d{1,2}$/.test(part)) {
      scales.add(Number(part));
    } else {
      return null;
    }
  }
  const sorted = [...scales].sort((a, b) => a - b);
  if (sorted.length === 0 || sorted.some((scale) => scale < 1 || scale > 19)) return null;
  return sorted;
}

/** "11 t/m 13": the scales of a group without the word in front. */
export function scaleTag(group: FunctionGroup): string {
  return group.scales_text.replace(/^schaal\s+/, '');
}

/** What a reload of the reference file did, in one line. */
export function reloadSummary(result: ReloadResult): string {
  const changed = result.groups_created + result.groups_updated + result.families_created;
  const kept =
    result.groups_kept > 0 ? ` ${result.groups_kept} met de hand gewijzigd en zo gelaten.` : '';
  if (changed === 0) return `Opnieuw geladen: gelijk aan het referentiebestand.${kept}`;
  return `Opnieuw geladen: ${result.groups_created} toegevoegd, ${result.groups_updated} bijgewerkt.${kept}`;
}
