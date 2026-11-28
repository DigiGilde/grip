import { useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  chooseExamplePerson,
  fetchAuthStatus,
  fetchExamplePersons,
  type ExamplePerson,
} from '@/api/auth';
import { AUTH_STATUS_KEY } from '@/auth/authState';
import { useNlddEvent } from '@/components/nldd/events';
import { useInstance } from './useInstance';

/**
 * An example instance: only fictional data, for showing grip.
 *
 * The server decides that an instance is an example (its mode, not its name)
 * and who a visitor is. A visitor logged in for real and looks as one of the
 * example persons; the choice is kept in the session on the server.
 */
const EXAMPLE_NOTICE = 'Voorbeeld: alle gegevens zijn verzonnen';

interface ExampleVisit {
  /** The name of who really logged in. */
  visitor: string;
  /** The example person they look as. */
  personId: string;
  personName: string;
}

export function useExampleVisit(): ExampleVisit | null {
  const instance = useInstance();
  const { data } = useQuery({
    // The answer the application already has about the reader.
    queryKey: AUTH_STATUS_KEY,
    queryFn: fetchAuthStatus,
    enabled: instance?.example === true,
    staleTime: 60_000,
    retry: false,
  });
  if (!data?.example_visitor || !data.person) return null;
  return { visitor: data.example_visitor, personId: data.person.id, personName: data.person.name };
}

/**
 * The bar above every screen of an example instance: that this is an
 * example, and for a visitor as whom they look. Nothing on an instance for
 * real work.
 *
 * One line that truncates at the end, so the word "Voorbeeld" goes first.
 */
export function ExampleStatusBar({ slot }: { slot: string }) {
  const instance = useInstance();
  const visit = useExampleVisit();
  if (!instance?.example) return null;
  return (
    <nldd-status-bar
      slot={slot}
      variant="warning"
      text={visit ? `${EXAMPLE_NOTICE} · je kijkt als ${visit.personName}` : EXAMPLE_NOTICE}
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
  const name = current ? `**${person.name}**` : person.name;
  // The role goes in the text, which wraps; `details` does not wrap and would
  // squeeze the name to one letter per line on a phone.
  return (
    <nldd-menu-item
      ref={ref}
      text={person.role ? `${name} · ${person.role}` : name}
      {...(current ? { details: 'Zo kijk je nu' } : {})}
    />
  );
}

function useExamplePersons(visit: ExampleVisit | null): ExamplePerson[] | undefined {
  return useQuery({
    queryKey: ['example-persons'],
    queryFn: fetchExamplePersons,
    enabled: visit !== null,
    staleTime: Infinity,
    retry: false,
  }).data;
}

/** Whether the menu group below draws anything, for a menu that holds nothing else. */
export function useCanSwitchExamplePerson(): boolean {
  const visit = useExampleVisit();
  const people = useExamplePersons(visit);
  return visit !== null && Boolean(people?.length);
}

/** The menu group for looking as another example person; only for a visitor. */
export function ExamplePersonSwitch() {
  const visit = useExampleVisit();
  const people = useExamplePersons(visit);
  if (!visit || !people?.length) return null;
  return (
    <nldd-menu-group text="Bekijk het voorbeeld als">
      {people.map((person) => (
        <PersonItem key={person.id} person={person} current={person.id === visit.personId} />
      ))}
    </nldd-menu-group>
  );
}
