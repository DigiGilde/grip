import { useRef } from "react";
import { createPortal } from "react-dom";
import { useQuery } from "@tanstack/react-query";
import { useNlddEvent } from "@/components/nldd/events";

/**
 * Local development only: act as another example person.
 *
 * Without an identity provider the backend runs as the first beheerder, or as
 * the person named in the cookie below. Screens differ per person (an owner
 * sees other actions than a beheerder or a team member), so looking around as
 * one person hides most of that. The menu group is absent as soon as an
 * identity provider is configured; the backend ignores the cookie then.
 */
const DEV_PERSON_COOKIE = "grip_dev_person";

interface DevPerson {
  id: string;
  name: string;
}

interface DevPeople {
  enabled: boolean;
  people: DevPerson[];
}

async function fetchDevPeople(): Promise<DevPeople> {
  const status = await fetch("/api/auth/status", {
    credentials: "same-origin",
  });
  if (!status.ok) return { enabled: false, people: [] };
  const body = (await status.json()) as { oidc_configured?: boolean };
  if (body.oidc_configured !== false) return { enabled: false, people: [] };
  // Listed as the default person (no cookie), so the list is the same
  // whoever is currently being viewed as.
  const people = await fetch("/api/people", { credentials: "omit" });
  if (!people.ok) return { enabled: true, people: [] };
  const data = (await people.json()) as { items?: DevPerson[] } | DevPerson[];
  const items = Array.isArray(data) ? data : (data.items ?? []);
  return { enabled: true, people: items.map(({ id, name }) => ({ id, name })) };
}

function switchTo(id: string | null): void {
  document.cookie = id
    ? `${DEV_PERSON_COOKIE}=${id}; path=/; SameSite=Lax`
    : `${DEV_PERSON_COOKIE}=; path=/; max-age=0`;
  window.location.reload();
}

function PersonItem({
  person,
  current,
}: {
  person: DevPerson;
  current: boolean;
}) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, "select", () => switchTo(person.id));
  return (
    <nldd-menu-item
      ref={ref}
      text={person.name}
      {...(current ? { "supporting-text": "Hier kijk je nu als" } : {})}
    />
  );
}

export function DevPersonSwitch({ currentId }: { currentId: string | null }) {
  const { data } = useQuery({
    queryKey: ["dev-people"],
    queryFn: fetchDevPeople,
    staleTime: Infinity,
    retry: false,
  });
  if (!data?.enabled || data.people.length === 0) return null;
  return (
    <nldd-menu-group text="Bekijk als (alleen lokaal)">
      {data.people.map((person) => (
        <PersonItem
          key={person.id}
          person={person}
          current={person.id === currentId}
        />
      ))}
    </nldd-menu-group>
  );
}

function viewingAsId(): string | null {
  const match = document.cookie.match(
    new RegExp(`(?:^|; )${DEV_PERSON_COOKIE}=([^;]+)`),
  );
  return match ? decodeURIComponent(match[1] ?? "") : null;
}

/**
 * A fixed note in the corner while acting as another example person, so it
 * is never unclear why a screen shows fewer tabs or actions than expected.
 */
export function DevPersonBadge({ name }: { name: string | null }) {
  const ref = useRef<HTMLButtonElement>(null);
  if (!name || viewingAsId() === null) return null;
  return createPortal(
    <div className="dev-person-badge" role="status">
      <span>
        Je bekijkt grip als <strong>{name}</strong> (alleen lokaal)
      </span>
      <button ref={ref} type="button" onClick={() => switchTo(null)}>
        Terug naar de beheerder
      </button>
    </div>,
    document.body,
  );
}
