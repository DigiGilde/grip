import { useEffect, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { errorMessage } from '@/api/client';
import { orUndef, useNlddEvent } from '@/components/nldd/events';
import { createRole, fetchRoles, roleKeys, type CatalogueRole } from './api';
import { hasExactRole, matchRoles } from './text';
import './nldd';

/** The menu value of the one action that is not a role. */
const ADD_ACTION = '__add__';

function eventValue(event: Event): string {
  const detail = (event as CustomEvent<{ value?: unknown }>).detail;
  const fromDetail = detail && typeof detail === 'object' ? detail.value : undefined;
  const value = fromDetail ?? (event.target as { value?: unknown } | null)?.value;
  return value === undefined || value === null ? '' : String(value);
}

export interface RolePickerProps {
  /** The label of the field, for example "Rol". */
  label: string;
  /**
   * The name of the chosen role, or null. The name is what a budget line
   * sends as its `role`; the server finds the role in the catalogue by it,
   * whatever the capitals.
   */
  value: string | null;
  /** Called with the chosen role, or null when the field is emptied. */
  onChange: (role: CatalogueRole | null) => void;
  supportingLabel?: string;
  optional?: boolean;
  invalid?: boolean;
  disabled?: boolean;
  /**
   * Set to false to never offer adding a role. By default the picker offers
   * it when nothing fits what was typed and the reader may add one.
   */
  allowAdd?: boolean;
  /** Roles to leave out, by id: the role itself when choosing what to merge it into. */
  exclude?: string[];
}

/**
 * Pick a role from the catalogue: the fixed list of roles people are staffed
 * in. Type to search. When no role has the name that was typed, and the
 * reader may add one, the last option adds it; the beheerder then sees it as
 * a role to review.
 */
export function RolePicker({
  label,
  value,
  onChange,
  supportingLabel,
  optional,
  invalid,
  disabled,
  allowAdd = true,
  exclude,
}: RolePickerProps) {
  const queryClient = useQueryClient();
  const ref = useRef<HTMLElement>(null);
  const [typed, setTyped] = useState('');
  const [problem, setProblem] = useState<string | null>(null);
  const [added, setAdded] = useState<string | null>(null);

  const query = useQuery({ queryKey: roleKeys.list(false), queryFn: () => fetchRoles(false) });
  const roles = (query.data?.items ?? []).filter((role) => !exclude?.includes(role.id));
  const mayAdd = allowAdd && !disabled && (query.data?.can_add ?? false);
  const matches = matchRoles(roles, typed);
  const typedName = typed.trim().replace(/\s+/g, ' ');
  const offerAdd = mayAdd && typedName !== '' && !hasExactRole(roles, typedName);

  // The element keeps its own value and text once the user has typed or
  // picked. Writing them here puts it back in step with what is chosen.
  const show = (text: string) => {
    const el = ref.current as (HTMLElement & { value?: string; text?: string }) | null;
    if (!el) return;
    el.value = text;
    el.text = text;
  };
  useEffect(() => {
    show(value ?? '');
  }, [value]);

  const add = useMutation({
    mutationFn: (name: string) => createRole({ name }),
    onSuccess: async (role) => {
      await queryClient.invalidateQueries({ queryKey: roleKeys.all });
      setProblem(null);
      setAdded(role.needs_review ? role.name : null);
      setTyped('');
      onChange(role);
    },
    onError: (error) => {
      setProblem(errorMessage(error));
      show(value ?? '');
    },
  });

  useNlddEvent(ref, 'input', (event) => {
    setTyped(eventValue(event));
    setProblem(null);
  });
  useNlddEvent(ref, 'change', (event) => {
    const picked = eventValue(event);
    if (picked === ADD_ACTION) {
      show(typedName);
      if (!add.isPending) add.mutate(typedName);
      return;
    }
    if (picked === '') {
      setAdded(null);
      if (value !== null) onChange(null);
      return;
    }
    const role = roles.find((item) => item.name === picked);
    if (role) {
      setTyped('');
      setAdded(null);
      onChange(role);
    }
  });

  return (
    <nldd-container gap="8">
      <nldd-form-field
        label={label}
        {...(supportingLabel ? { 'supporting-label': supportingLabel } : {})}
        optional={orUndef(optional)}
      >
        <nldd-combo-box
          ref={ref}
          no-filter
          accessible-label={label}
          placeholder="Zoek een rol"
          invalid={orUndef(invalid)}
          disabled={orUndef(disabled)}
        >
          <nldd-menu
            empty-text={
              query.isError ? 'De rollen konden niet worden geladen' : 'Geen rol met deze naam'
            }
          >
            {matches.map((role) => (
              <nldd-menu-item
                key={role.id}
                value={role.name}
                text={role.name}
                {...(role.description ? { details: role.description } : {})}
              />
            ))}
            {offerAdd ? (
              <>
                {matches.length > 0 ? <nldd-menu-divider /> : null}
                <nldd-menu-item
                  value={ADD_ACTION}
                  icon="plus"
                  text={`Staat er niet tussen? Voeg "${typedName}" toe als rol`}
                />
              </>
            ) : null}
          </nldd-menu>
        </nldd-combo-box>
      </nldd-form-field>
      {problem ? <nldd-banner variant="critical" text={problem} /> : null}
      {added ? (
        <nldd-banner
          variant="info"
          text={`De rol "${added}" is toegevoegd`}
          supporting-text="De beheerder bekijkt nieuwe rollen en voegt ze samen als er al een rol voor bestond."
        />
      ) : null}
    </nldd-container>
  );
}
