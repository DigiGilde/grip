import { useRef } from "react";
import { useNlddEvent } from "@/components/nldd/events";
import { useAuth } from "@/auth/context";
import { DevPersonBadge, DevPersonSwitch } from "./DevPersonSwitch";

interface LogoutItemProps {
  slot?: string;
}

/** "Uitloggen" as a menu item; `select` does not reach React's own handlers. */
export function LogoutMenuItem({ slot }: LogoutItemProps) {
  const { logout } = useAuth();
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, "select", logout);
  return (
    <nldd-menu-item
      ref={ref}
      {...(slot ? { slot } : {})}
      icon="logout"
      text="Uitloggen"
    />
  );
}

interface AccountMenuProps {
  /** Where the menu opens: below the button in a top bar, above it in a bottom bar. */
  placement: "bottom-end" | "top-end";
}

/** The account button of the main toolbar, with the menu behind it. */
export function AccountMenu({ placement }: AccountMenuProps) {
  const { state } = useAuth();
  const person = state.status === "authenticated" ? state.person : null;

  return (
    <>
      <DevPersonBadge name={person?.name ?? null} />
      <nldd-icon-button icon="account" text="Account" expandable>
        <nldd-menu slot="popup" placement={placement}>
          {person && (
            <nldd-menu-group text={person.name}>
              <LogoutMenuItem />
            </nldd-menu-group>
          )}
          {!person && <LogoutMenuItem />}
          <DevPersonSwitch currentId={person?.id ?? null} />
        </nldd-menu>
      </nldd-icon-button>
    </>
  );
}
