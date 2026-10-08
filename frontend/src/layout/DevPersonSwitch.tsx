import { useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNlddEvent } from '@/components/nldd/events';

/**
 * Local development only: act as another example person.
 *
 * Without an identity provider the backend runs as the first beheerder, or as
 * the person named in the cookie below. Screens differ per person (an owner
 * sees other actions than a beheerder or a team member), so looking around as
 * one person hides most of that. Everything here is absent as soon as an
 * identity provider is configured; the backend ignores the cookie then.
 */
const DEV_PERSON_COOKIE = 'grip_dev_person';

interface DevPerson {
  id: string;
  name: string;
}

interface DevPeople {
  enabled: boolean;
  people: DevPerson[];
}

async function fetchDevPeople(): Promise<DevPeople> {
  const status = await fetch('/api/auth/status', {
    credentials: 'same-origin',
  });
  if (!status.ok) return { enabled: false, people: [] };
  const body = (await status.json()) as { oidc_configured?: boolean };
  if (body.oidc_configured !== false) return { enabled: false, people: [] };
  // Listed as the default person (no cookie), so the list is the same
  // whoever is currently being viewed as.
  const people = await fetch('/api/people', { credentials: 'omit' });
  if (!people.ok) return { enabled: true, people: [] };
  const data = (await people.json()) as { items?: DevPerson[] } | DevPerson[];
  const items = Array.isArray(data) ? data : (data.items ?? []);
  return { enabled: true, people: items.map(({ id, name }) => ({ id, name })) };
}

function useDevPeople(): DevPeople | undefined {
  return useQuery({
    queryKey: ['dev-people'],
    queryFn: fetchDevPeople,
    staleTime: Infinity,
    retry: false,
  }).data;
}

function switchTo(id: string | null): void {
  document.cookie = id
    ? `${DEV_PERSON_COOKIE}=${id}; path=/; SameSite=Lax`
    : `${DEV_PERSON_COOKIE}=; path=/; max-age=0`;
  window.location.reload();
}

function viewingAsId(): string | null {
  const match = document.cookie.match(new RegExp(`(?:^|; )${DEV_PERSON_COOKIE}=([^;]+)`));
  return match ? decodeURIComponent(match[1] ?? '') : null;
}

/**
 * True while the local session acts as a chosen example person. The account
 * button says so in the bar itself, so it is never unclear why a screen shows
 * fewer sections or actions than expected.
 */
export function useViewingAs(): boolean {
  const people = useDevPeople();
  return people?.enabled === true && viewingAsId() !== null;
}

function PersonItem({ person, current }: { person: DevPerson; current: boolean }) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'select', () => switchTo(person.id));
  return (
    <nldd-menu-item
      ref={ref}
      text={current ? `**${person.name}**` : person.name}
      {...(current ? { details: 'Zo kijk je nu' } : {})}
    />
  );
}

function BackItem() {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'select', () => switchTo(null));
  return <nldd-menu-item ref={ref} icon="arrow-u-turn-backward" text="Terug naar de beheerder" />;
}

/** The menu group for acting as someone else; nothing outside local development. */
export function DevPersonSwitch({ currentId }: { currentId: string | null }) {
  const data = useDevPeople();
  if (!data?.enabled || data.people.length === 0) return null;
  return (
    <nldd-menu-group text="Bekijk als (alleen lokaal)">
      {viewingAsId() !== null && <BackItem />}
      {data.people.map((person) => (
        <PersonItem key={person.id} person={person} current={person.id === currentId} />
      ))}
    </nldd-menu-group>
  );
}
