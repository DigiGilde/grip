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
 * by the same state, and the primary action is the last to move.
 *
 *     <ActionBar
 *       label="Inzet filteren"
 *       filters={[{ label: 'Jaar', value, onChange, options }]}
 *       actions={[{ text: 'Nieuwe inzet', onClick, primary: true }]}
 *     />
 */
import { useRef } from 'react';
import { orUndef, useNlddEvent } from '@/components/nldd/events';
import { iconAttribute } from './icons';

if (import.meta.env.MODE !== 'test') {
  void import('@nldd/design-system/dropdown');
  void import('@nldd/design-system/link');
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
    <nldd-toolbar-item slot="start" priority={1}>
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

function ActionItem({ action }: { action: ActionBarAction }) {
  const buttonRef = useRef<HTMLElement>(null);
  const menuRef = useRef<HTMLElement>(null);
  const onClick = action.href ? undefined : () => action.onClick?.();
  useNlddEvent(buttonRef, 'click', onClick);
  useNlddEvent(menuRef, 'select', onClick);
  const appearance = action.primary ? 'primary' : 'secondary';
  return (
    <nldd-toolbar-item slot="end" priority={action.primary ? 3 : 2}>
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

interface ActionBarProps {
  /** Accessible name of the row, e.g. "Inzet filteren". */
  label: string;
  filters?: readonly ActionBarFilter[];
  actions?: readonly ActionBarAction[];
}

export function ActionBar({ label, filters = [], actions = [] }: ActionBarProps) {
  if (filters.length === 0 && actions.length === 0) return null;
  return (
    <nldd-toolbar size={SIZE} label={label}>
      {filters.map((filter) => (
        <FilterItem key={filter.label} filter={filter} />
      ))}
      {actions.map((action) => (
        <ActionItem key={action.text} action={action} />
      ))}
    </nldd-toolbar>
  );
}
