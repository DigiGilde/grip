import { useEffect, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { errorMessage } from '@/api/client';
import { orUndef, useNlddEvent } from '@/components/nldd/events';
import {
  createOrganisation,
  fetchOrganisation,
  organisationKeys,
  searchOrganisations,
  type Organisation,
} from './api';
import { organisationDetails, organisationText } from './text';
import './nldd';

/** The menu value of the one action that is not an organisation. */
const ADD_ACTION = '__add__';
const SEARCH_DELAY_MS = 200;
const RESULTS = 12;

function eventValue(event: Event): string {
  const detail = (event as CustomEvent<{ value?: unknown }>).detail;
  const fromDetail = detail && typeof detail === 'object' ? detail.value : undefined;
  const value = fromDetail ?? (event.target as { value?: unknown } | null)?.value;
  return value === undefined || value === null ? '' : String(value);
}

function useDebounced(value: string, delay: number): string {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delay);
    return () => window.clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

interface SearchFieldProps {
  /** The chosen organisation, or null. */
  selected: Organisation | null;
  onSelect: (organisation: Organisation | null) => void;
  accessibleLabel: string;
  /** Only organisations of this type, for example "Ministerie". */
  type?: string;
  invalid?: boolean;
  disabled?: boolean;
  /** Called with what was typed when the user asks to add an organisation. */
  onAdd?: (typed: string) => void;
}

/**
 * The combo box itself: type to search, the server filters and ranks. Used
 * for the picker and, without the add action, for the parent in its form.
 */
function SearchField({
  selected,
  onSelect,
  accessibleLabel,
  type,
  invalid,
  disabled,
  onAdd,
}: SearchFieldProps) {
  const ref = useRef<HTMLElement>(null);
  const [typed, setTyped] = useState('');
  const query = useDebounced(typed.trim(), SEARCH_DELAY_MS);
  const results = useQuery({
    queryKey: organisationKeys.search({ q: query, type, page_size: RESULTS }),
    queryFn: () => searchOrganisations({ q: query, type, page_size: RESULTS }),
    placeholderData: (previous) => previous,
  });
  const items = results.data?.items ?? [];
  const selectedText = selected ? organisationText(selected) : '';

  // The element keeps its own value and text once the user has typed or
  // picked. Writing them here puts it back in step with what is chosen.
  const show = (value: string, text: string) => {
    const el = ref.current as (HTMLElement & { value?: string; text?: string }) | null;
    if (!el) return;
    el.value = value;
    el.text = text;
  };
  useEffect(() => {
    show(selected?.id ?? '', selectedText);
  }, [selected?.id, selectedText]);

  useNlddEvent(ref, 'input', (event) => setTyped(eventValue(event)));
  useNlddEvent(ref, 'change', (event) => {
    const value = eventValue(event);
    if (value === ADD_ACTION) {
      show(selected?.id ?? '', selectedText);
      onAdd?.(typed.trim());
      return;
    }
    if (value === '') {
      if (selected) onSelect(null);
      return;
    }
    const picked = items.find((item) => item.id === value);
    if (picked) {
      setTyped('');
      onSelect(picked);
    }
  });

  return (
    <nldd-combo-box
      ref={ref}
      no-filter
      accessible-label={accessibleLabel}
      placeholder="Zoek op naam of afkorting"
      invalid={orUndef(invalid)}
      disabled={orUndef(disabled)}
    >
      <nldd-menu
        empty-text={results.isError ? 'De organisaties konden niet worden geladen' : 'Niets gevonden'}
      >
        {items.map((item) => (
          <nldd-menu-item
            key={item.id}
            value={item.id}
            text={organisationText(item)}
            details={organisationDetails(item)}
          />
        ))}
        {onAdd ? (
          <>
            {items.length > 0 ? <nldd-menu-divider /> : null}
            <nldd-menu-item
              value={ADD_ACTION}
              icon="plus"
              text="Staat er niet tussen? Voeg een organisatie toe"
            />
          </>
        ) : null}
      </nldd-menu>
    </nldd-combo-box>
  );
}

interface AddFormProps {
  initialName: string;
  onAdded: (organisation: Organisation) => void;
  onCancel: () => void;
}

/**
 * The small form behind "Staat er niet tussen?": a name and, for a unit of
 * an existing organisation, what it belongs to. Not a <form> element: the
 * picker usually sits inside one already, and forms do not nest.
 */
export function AddOrganisationForm({ initialName, onAdded, onCancel }: AddFormProps) {
  const queryClient = useQueryClient();
  const nameRef = useRef<HTMLElement>(null);
  const addRef = useRef<HTMLElement>(null);
  const cancelRef = useRef<HTMLElement>(null);
  const [name, setName] = useState(initialName);
  const [parent, setParent] = useState<Organisation | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  const add = useMutation({
    mutationFn: () => createOrganisation({ name: name.trim(), parent_id: parent?.id ?? null }),
    onSuccess: async (organisation) => {
      await queryClient.invalidateQueries({ queryKey: organisationKeys.all });
      onAdded(organisation);
    },
    onError: (error) => setProblem(errorMessage(error)),
  });
  const submit = () => {
    if (add.isPending) return;
    if (!name.trim()) {
      setProblem('Geef de organisatie een naam.');
      return;
    }
    setProblem(null);
    add.mutate();
  };

  useEffect(() => {
    nameRef.current?.focus();
  }, []);
  useNlddEvent(nameRef, 'input', (event) => setName(eventValue(event)));
  // Enter in the name adds the organisation instead of sending the form the
  // picker sits in.
  useNlddEvent(nameRef, 'keydown', (event) => {
    if ((event as KeyboardEvent).key === 'Enter') {
      event.preventDefault();
      event.stopPropagation();
      submit();
    }
  });
  useNlddEvent(addRef, 'click', submit);
  useNlddEvent(cancelRef, 'click', onCancel);

  return (
    <nldd-container gap="16" padding="16" role="group" aria-label="Organisatie toevoegen">
      <nldd-title size={5} text="Organisatie toevoegen" heading-level={3} />
      {problem ? <nldd-banner variant="critical" text={problem} /> : null}
      <nldd-form-field
        label="Naam"
        supporting-label="Voor een partij die niet in het overheidsregister staat, of een eenheid binnen een organisatie"
      >
        <nldd-text-field ref={nameRef} value={name} required />
      </nldd-form-field>
      <nldd-form-field
        label="Hoort bij"
        supporting-label="Kies de organisatie waar deze eenheid onder valt"
        optional
      >
        <SearchField
          selected={parent}
          onSelect={setParent}
          accessibleLabel="Hoort bij"
        />
      </nldd-form-field>
      <nldd-container layout="wrap" gap="8">
        <nldd-button
          ref={addRef}
          type="button"
          appearance="primary"
          text="Voeg toe"
          loading={orUndef(add.isPending)}
        />
        <nldd-button ref={cancelRef} type="button" appearance="secondary" text="Annuleer" />
      </nldd-container>
    </nldd-container>
  );
}

export interface OrganisationPickerProps {
  /** The label of the field, for example "Opdrachtgever". */
  label: string;
  /** Id of the chosen organisation, or null. */
  value: string | null;
  /**
   * Called with the chosen organisation, or null when the field is emptied.
   * Keep `organisation.id` as the value; the rest is there to show.
   */
  onChange: (organisation: Organisation | null) => void;
  supportingLabel?: string;
  optional?: boolean;
  invalid?: boolean;
  disabled?: boolean;
  /** Only organisations of this type, for example "Ministerie". */
  type?: string;
  /** Set to false to leave out "Staat er niet tussen?". Default true. */
  allowAdd?: boolean;
}

/**
 * Pick an organisation from the whole list: the government's organisations
 * from the public register plus what was added by hand. Type a name or an
 * abbreviation; each result shows where it sits, so equal names can be told
 * apart. When nothing fits, the last option adds an organisation.
 */
export function OrganisationPicker({
  label,
  value,
  onChange,
  supportingLabel,
  optional,
  invalid,
  disabled,
  type,
  allowAdd = true,
}: OrganisationPickerProps) {
  // The organisation behind `value`: what the user just picked, or fetched
  // when the form opens on a record that already has one.
  const [picked, setPicked] = useState<Organisation | null>(null);
  const known = picked && picked.id === value ? picked : null;
  const fetched = useQuery({
    queryKey: organisationKeys.one(value ?? ''),
    queryFn: () => fetchOrganisation(value ?? ''),
    enabled: value !== null && known === null,
  });
  const selected = value === null ? null : (known ?? fetched.data ?? null);
  const [adding, setAdding] = useState<string | null>(null);

  const choose = (organisation: Organisation | null) => {
    setPicked(organisation);
    onChange(organisation);
  };

  return (
    <nldd-container gap="8">
      <nldd-form-field
        label={label}
        {...(supportingLabel ? { 'supporting-label': supportingLabel } : {})}
        optional={orUndef(optional)}
      >
        <SearchField
          selected={selected}
          onSelect={choose}
          accessibleLabel={label}
          type={type}
          invalid={invalid}
          disabled={disabled}
          onAdd={allowAdd && !disabled ? (typed) => setAdding(typed) : undefined}
        />
      </nldd-form-field>
      {adding !== null ? (
        <AddOrganisationForm
          key={adding}
          initialName={adding}
          onAdded={(organisation) => {
            setAdding(null);
            choose(organisation);
          }}
          onCancel={() => setAdding(null)}
        />
      ) : null}
    </nldd-container>
  );
}
