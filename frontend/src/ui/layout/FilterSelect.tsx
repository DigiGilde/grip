/**
 * One select on its own, at the same size step as the fields and buttons
 * around it. For a row of filters next to an action use `@/ui/ActionBar`.
 */
if (import.meta.env.MODE !== 'test') void import('@nldd/design-system/dropdown');

interface FilterSelectProps {
  /** Accessible name; the select has no visible label. */
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: readonly { value: string; label: string }[];
  width?: string;
}

export function FilterSelect({ label, value, onChange, options, width }: FilterSelectProps) {
  return (
    <nldd-dropdown accessible-label={label} {...(width ? { width } : {})}>
      <select value={value} aria-label={label} onChange={(event) => onChange(event.target.value)}>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </nldd-dropdown>
  );
}
