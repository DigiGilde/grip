import type { Allocation } from './api';

export type Grouping = 'person' | 'line';

export interface AllocationGroup {
  key: string;
  title: string;
  /** Says where the group belongs, e.g. the assignment of a budget line. */
  subtitle: string;
  items: Allocation[];
}

/** Rows grouped per person or per budget line, groups and rows in a stable order. */
export function groupAllocations(items: readonly Allocation[], grouping: Grouping): AllocationGroup[] {
  const groups = new Map<string, AllocationGroup>();
  for (const item of items) {
    const key =
      grouping === 'person' ? item.person_id : (item.budget_line_id ?? `unknown-${item.id}`);
    let group = groups.get(key);
    if (!group) {
      group =
        grouping === 'person'
          ? { key, title: item.person_name, subtitle: '', items: [] }
          : {
              key,
              title: item.budget_line_description ?? 'Begrotingsregel',
              subtitle: item.assignment_name ?? '',
              items: [],
            };
      groups.set(key, group);
    }
    group.items.push(item);
  }
  return [...groups.values()].sort(
    (a, b) => a.subtitle.localeCompare(b.subtitle, 'nl') || a.title.localeCompare(b.title, 'nl'),
  );
}

/** What the R14 signal says, with the categories when the reader may see them. */
export function mismatchText(item: Allocation): string {
  if (!item.category_mismatch) return '';
  if (item.person_category && item.line_category) {
    return `Declareert in categorie ${item.person_category}; de regel rekent met ${item.line_category}`;
  }
  return 'Declareert in een andere categorie dan de regel aanneemt';
}
