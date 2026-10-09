import { useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  chooseExamplePerson,
  fetchExamplePersons,
  type AuthStatus,
  type ExamplePerson,
} from '@/api/auth';
import { apiGet } from '@/api/client';
import { useNlddEvent } from '@/components/nldd/events';
import { useInstance } from './useInstance';

/**
 * An example instance: only fictional data, for showing grip.
 *
 * The server decides that an instance is an example (its mode, not its name)
 * and who a visitor is. A visitor logged in for real and looks as one of the
 * example persons; the choice is kept in the session on the server.
 */
const EXAMPLE_NOTICE = 'Voorbeeld: alle gegevens zijn verzonnen.';

interface ExampleVisit {
  /** The name of who really logged in. */
  visitor: string;
  /** The example person they look as. */
  personId: string;
  personName: string;
}

function useExampleVisit(): ExampleVisit | null {
  const instance = useInstance();
  const { data } = useQuery({
    queryKey: ['example-visit'],
    queryFn: () => apiGet<AuthStatus>('/api/auth/status'),
    enabled: instance?.example === true,
    staleTime: Infinity,
    retry: false,
  });
  if (!data?.example_visitor || !data.person) return null;
  return { visitor: data.example_visitor, personId: data.person.id, personName: data.person.name };
}

/**
 * The line every page of an example instance carries: that this is an
 * example, and for a visitor as whom they look. Nothing on an instance for
 * real work.
 */
export function ExampleNotice() {
  const instance = useInstance();
  const visit = useExampleVisit();
  if (!instance?.example) return null;
  return (
    <nldd-banner
      variant="warning"
      size="sm"
      text={visit ? `Je bekijkt het voorbeeld als ${visit.personName}` : EXAMPLE_NOTICE}
      {...(visit ? { 'supporting-text': `${EXAMPLE_NOTICE} Ingelogd als ${visit.visitor}.` } : {})}
      data-state="example"
    />
  );
}

function PersonItem({ person, current }: { person: ExamplePerson; current: boolean }) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'select', () => {
    // The server keeps the choice; every screen is loaded again as that person.
    void chooseExamplePerson(person.id).then(() => window.location.reload());
  });
  return (
    <nldd-menu-item
      ref={ref}
      text={current ? `**${person.name}**` : person.name}
      {...(current ? { details: 'Zo kijk je nu' } : {})}
    />
  );
}

/** The menu group for looking as another example person; only for a visitor. */
export function ExamplePersonSwitch() {
  const visit = useExampleVisit();
  const { data: people } = useQuery({
    queryKey: ['example-persons'],
    queryFn: fetchExamplePersons,
    enabled: visit !== null,
    staleTime: Infinity,
    retry: false,
  });
  if (!visit || !people?.length) return null;
  return (
    <nldd-menu-group text="Bekijk het voorbeeld als">
      {people.map((person) => (
        <PersonItem key={person.id} person={person} current={person.id === visit.personId} />
      ))}
    </nldd-menu-group>
  );
}
