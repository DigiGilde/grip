import { useRef, useState } from 'react';
import { orUndef, useNlddEvent } from '@/components/nldd/events';
import { searchGroups, suggestedFirst, type GroupChoice } from './api';

// Tests leave the nldd-* elements unregistered on purpose (see the vacancy
// bindings); elements upgrade whenever their definition arrives.
if (import.meta.env.MODE !== 'test') void import('@nldd/design-system/combo-box');

interface FunctionGroupPickerProps {
  label: string;
  hint?: string;
  choices: GroupChoice[];
  /** The id of the chosen group, or '' for none. */
  value: string;
  onChange: (groupId: string) => void;
  /** Scales to suggest groups for, e.g. those of the budget line's category. */
  suggestScales?: number[] | null;
  /** Shown in the field while no group of the list is chosen. */
  currentText?: string;
  optional?: boolean;
}

/**
 * Search and select a function group of the Functiegebouw Rijk. Typing
 * filters on the names of groups and of families; groups that fit the
 * suggested scales come first.
 */
export function FunctionGroupPicker({
  label,
  hint,
  choices,
  value,
  onChange,
  suggestScales,
  currentText,
  optional,
}: FunctionGroupPickerProps) {
  const ref = useRef<HTMLElement>(null);
  const [query, setQuery] = useState('');
  const chosen = choices.find((choice) => choice.id === value);

  useNlddEvent(ref, 'input', (event) => {
    const detail = (event as CustomEvent<{ value?: string }>).detail;
    setQuery(detail?.value ?? '');
  });
  useNlddEvent(ref, 'change', (event) => {
    const detail = (event as CustomEvent<{ value?: string }>).detail;
    const picked = detail?.value ?? '';
    // Only a group of the list counts; clearing the field clears the choice.
    if (picked === '' || choices.some((choice) => choice.id === picked)) {
      onChange(picked);
      setQuery('');
    }
  });

  // While the field shows the chosen group, the whole list stays available.
  const matches = searchGroups(choices, chosen && query === chosen.name ? '' : query);
  const { suggested, others } = suggestedFirst(matches, suggestScales);
  const item = (choice: GroupChoice) => (
    <nldd-menu-item
      key={choice.id}
      value={choice.id}
      text={choice.name}
      details={`${choice.family_name}, ${choice.scales_text}`}
      selected={orUndef(choice.id === value)}
    />
  );

  return (
    <nldd-form-field
      label={label}
      optional={orUndef(optional)}
      {...(hint ? { 'supporting-label': hint } : {})}
    >
      <nldd-combo-box
        ref={ref}
        value={value}
        text={chosen?.name ?? currentText ?? ''}
        placeholder="Zoek op functiegroep of functiefamilie"
        max-items={10}
        no-filter
      >
        <nldd-menu>
          {suggested.length > 0 && (
            <nldd-menu-group text="Past bij de begrotingsregel">{suggested.map(item)}</nldd-menu-group>
          )}
          {suggested.length > 0 && others.length > 0 ? (
            <nldd-menu-group text="Overige functiegroepen">{others.map(item)}</nldd-menu-group>
          ) : (
            others.map(item)
          )}
        </nldd-menu>
      </nldd-combo-box>
    </nldd-form-field>
  );
}
