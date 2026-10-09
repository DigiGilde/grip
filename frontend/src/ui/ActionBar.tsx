/**
 * Filters on the left, actions on the right, in one row.
 *
 * Every control in the row is drawn at the same size step because the row is
 * a design-system toolbar, which sets the size of the controls in it. Use
 * this instead of placing a select next to a button yourself: two controls
 * placed by hand each keep their own default size, and then they differ in
 * height.
 *
 * On a narrow screen the toolbar moves what does not fit into its overflow
 * menu. Every filter and action therefore also exists as menu items, driven
 * by the same state. Secondary actions move first, then the filters, and the
 * primary action last: what the page shows stays choosable beside the menu.
 *
 *     <ActionBar
 *       label="Inzet filteren"
 *       filters={[{ label: 'Jaar', value, onChange, options }]}
 *       actions={[{ text: 'Nieuwe inzet', onClick, primary: true }]}
 *     />
 */
import { RowMenu, type RowAction } from '@/ui/RowActions';
import { useRef } from 'react';
import { orUndef, useNlddEvent } from '@/components/nldd/events';
import { iconAttribute } from './icons';
import { useNarrow } from './layout/useNarrow';
import { usePrimaryTaken } from './primary';

if (import.meta.env.MODE !== 'test') {
  void import('@nldd/design-system/dropdown');
  void import('@nldd/design-system/link');
  void import('@nldd/design-system/search-field');
}

/** The one size step of everything in the row. */
const SIZE = 'md';

export interface ActionBarOption {
  value: string;
  label: string;
}

export interface ActionBarFilter {
  /** Accessible name of the select, and the heading of its menu group. */
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: readonly ActionBarOption[];
  width?: string;
}

export interface ActionBarAction {
  text: string;
  onClick?: () => void;
  /** A download or a page: rendered as a link styled as a button. */
  href?: string;
  /**
   * What the link does when it leaves the page: `download` saves a file,
   * `elsewhere` opens a new tab. Each gets its fixed icon; other actions
   * have none, because their verb says it.
   */
  kind?: 'download' | 'elsewhere';
  primary?: boolean;
  loading?: boolean;
  /** Held while something else has to finish first. */
  disabled?: boolean;
}

function eventValue(event: Event): string {
  const detail = (event as CustomEvent<{ value?: unknown }>).detail;
  if (detail && detail.value !== undefined && detail.value !== null) return String(detail.value);
  const target = event.target as { value?: unknown } | null;
  return target?.value === undefined || target.value === null ? '' : String(target.value);
}

function OverflowOption({
  option,
  selected,
  onSelect,
}: {
  option: ActionBarOption;
  selected: boolean;
  onSelect: (value: string) => void;
}) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'select', () => onSelect(option.value));
  return <nldd-menu-item ref={ref} type="radio" text={option.label} selected={orUndef(selected)} />;
}

function FilterItem({ filter }: { filter: ActionBarFilter }) {
  const ref = useRef<HTMLElement>(null);
  // The dropdown stops the native change event and sends its own.
  useNlddEvent(ref, 'change', (event) => filter.onChange(eventValue(event)));
  return (
    <nldd-toolbar-item slot="start" priority={2}>
      <nldd-dropdown
        ref={ref}
        size={SIZE}
        accessible-label={filter.label}
        {...(filter.width ? { width: filter.width } : {})}
      >
        <select
          value={filter.value}
          aria-label={filter.label}
          onChange={(event) => filter.onChange(event.target.value)}
        >
          {filter.options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </nldd-dropdown>
      <nldd-menu-group slot="overflow" text={filter.label}>
        {filter.options.map((option) => (
          <OverflowOption
            key={option.value}
            option={option}
            selected={option.value === filter.value}
            onSelect={filter.onChange}
          />
        ))}
      </nldd-menu-group>
    </nldd-toolbar-item>
  );
}

/** Words to look for in the list below the bar. */
export interface ActionBarSearch {
  /** What can be searched: "Zoek op opdracht of opdrachtgever". */
  label: string;
  value: string;
  onChange: (value: string) => void;
  width?: string;
}

/** Below this width the search stands on a row of its own, above the bar. */
const NARROW = '(max-width: 720px)';

function SearchField({ search, width }: { search: ActionBarSearch; width?: string }) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'input', (event) => search.onChange(eventValue(event)));
  return (
    <nldd-search-field
      ref={ref}
      size={SIZE}
      {...(width ? { width } : {})}
      value={search.value}
      placeholder={search.label}
      accessible-label={search.label}
    />
  );
}

function ActionItem({ action }: { action: ActionBarAction }) {
  const buttonRef = useRef<HTMLElement>(null);
  const menuRef = useRef<HTMLElement>(null);
  const onClick = action.href ? undefined : () => action.onClick?.();
  useNlddEvent(buttonRef, 'click', onClick);
  useNlddEvent(menuRef, 'select', onClick);
  const taken = usePrimaryTaken();
  const appearance = action.primary && !taken ? 'primary' : 'secondary';
  return (
    <nldd-toolbar-item slot="end" priority={action.primary ? 3 : 1}>
      <nldd-button
        ref={buttonRef}
        size={SIZE}
        appearance={appearance}
        text={action.text}
        loading={orUndef(action.loading)}
        disabled={orUndef(action.disabled)}
        {...(action.href ? { href: action.href } : {})}
        {...(action.kind === 'elsewhere' ? { target: '_blank' } : {})}
        {...iconAttribute(action.kind)}
      />
      <nldd-menu-item
        ref={menuRef}
        slot="overflow"
        text={action.text}
        disabled={orUndef(action.disabled)}
        {...(action.href ? { href: action.href } : {})}
      />
    </nldd-toolbar-item>
  );
}

/** What a page can do besides its few buttons: one quiet menu at the end of the bar. */
export interface ActionBarMore {
  /** What the menu is about: "Meer acties voor <name>". */
  name: string;
  actions: readonly RowAction[];
}

interface ActionBarProps {
  /** Accessible name of the row, e.g. "Inzet filteren". */
  label: string;
  /** Searching the list, before the filters. */
  search?: ActionBarSearch;
  filters?: readonly ActionBarFilter[];
  actions?: readonly ActionBarAction[];
  /**
   * Actions that are rare or cannot be undone. They stand in a menu behind
   * one quiet button, so the bar keeps to what is done often; a destructive
   * one asks for confirmation there.
   */
  more?: ActionBarMore;
}

export function ActionBar({ label, search, filters = [], actions = [], more }: ActionBarProps) {
  const narrow = useNarrow(NARROW);
  const extra = more && more.actions.length > 0 ? more : null;
  if (!search && filters.length === 0 && actions.length === 0 && !extra) return null;
  const bar = (
    <nldd-toolbar size={SIZE} label={label}>
      {search && !narrow && (
        <nldd-toolbar-item slot="start" priority={3}>
          <SearchField search={search} width={search.width ?? '320px'} />
        </nldd-toolbar-item>
      )}
      {filters.map((filter) => (
        <FilterItem key={filter.label} filter={filter} />
      ))}
      {actions.map((action) => (
        <ActionItem key={action.text} action={action} />
      ))}
      {extra && (
        <nldd-toolbar-item slot="end" priority={1}>
          <RowMenu name={extra.name} actions={[...extra.actions]} size={SIZE} />
        </nldd-toolbar-item>
      )}
    </nldd-toolbar>
  );
  if (!search || !narrow) return bar;
  // A search field has no place in the bar's overflow menu: on a narrow
  // screen it keeps its own row, over the full width, and the bar follows.
  const rest = filters.length > 0 || actions.length > 0 || extra;
  return (
    <nldd-container gap="8">
      <SearchField search={search} />
      {rest ? bar : null}
    </nldd-container>
  );
}
