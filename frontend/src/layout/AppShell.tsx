import { Outlet } from 'react-router-dom';
import { PATHS } from '@/paths';
import { AccountMenu, LogoutMenuItem } from './AccountMenu';
import { MainNavigation, MainNavigationOverflow, NavigationMenuButton } from './MainNavigation';
import { useInstance } from './useInstance';
import { useRouteFocus } from './useRouteFocus';
import './shell.css';

const MAIN_CONTENT_ID = 'inhoud';

// `above` and `only` are read off a pane by nldd-bar-split-view, which is why
// the package types them on the parent and not on nldd-split-view-pane. Spread
// as plain attributes until the package's types cover them.
const FROM_LG: object = { above: 'lg' };
const ONLY_MD: object = { only: 'md' };
const ONLY_SM: object = { only: 'sm' };

/**
 * The bar below the widest breakpoint: the sections behind one menu button
 * that names the section you are in, and the account as an icon. The name of
 * the instance stands beside it while there is room, and goes on a phone.
 */
function NarrowToolbar({ instanceName, withName }: { instanceName: string; withName?: boolean }) {
  return (
    <nldd-container padding="8">
      <nldd-toolbar label={instanceName}>
        <nldd-toolbar-item slot="start" priority={3}>
          <NavigationMenuButton />
          <MainNavigationOverflow />
        </nldd-toolbar-item>
        {withName && (
          <nldd-toolbar-title slot="start" text={instanceName} href={PATHS.statusOverview} />
        )}
        <nldd-toolbar-item slot="end" priority={2}>
          <AccountMenu placement="bottom-end" compact />
          <LogoutMenuItem slot="overflow" />
        </nldd-toolbar-item>
      </nldd-toolbar>
    </nldd-container>
  );
}

/**
 * The application shell: a main toolbar around one content pane.
 *
 * Follows the design system's application pattern. The toolbar sits in its own
 * bar of the bar split view rather than in the pane, so it belongs to the whole
 * screen and does not scroll with the content.
 *
 * The bar reads from left to right as: where you are (the organisation's grip,
 * a link to the start), the work (the sections, as links), and at the end what
 * is not daily work: the settings of the instance and who you are. Below the
 * widest breakpoint the sections fold into one menu button that names the
 * section you are in, and the account shrinks to its icon.
 */
export function AppShell() {
  const instance = useInstance();
  useRouteFocus();

  const instanceName = instance?.name ?? 'Grip';

  return (
    <>
      <nldd-skip-link href={`#${MAIN_CONTENT_ID}`} text="Direct naar de inhoud" />
      <nldd-app-view>
        <nldd-bar-split-view>
          <nldd-split-view-pane slot="toolbar-wide" {...FROM_LG}>
            <nldd-container padding="8">
              <nldd-toolbar label={instanceName}>
                <nldd-toolbar-title slot="start" text={instanceName} href={PATHS.statusOverview} />
                {/* Fluid: the menu bar gets the room that is left and puts what does not fit behind its own button. */}
                <nldd-toolbar-item slot="start" priority={3} min-width="200px">
                  <MainNavigation area="work" label="Hoofdnavigatie" />
                  <MainNavigationOverflow area="work" />
                </nldd-toolbar-item>
                <nldd-toolbar-item slot="end" priority={1}>
                  <MainNavigation area="settings" label="Instellingen" />
                  <MainNavigationOverflow area="settings" />
                </nldd-toolbar-item>
                <nldd-toolbar-item slot="end" priority={2}>
                  <AccountMenu placement="bottom-end" />
                  <LogoutMenuItem slot="overflow" />
                </nldd-toolbar-item>
              </nldd-toolbar>
            </nldd-container>
          </nldd-split-view-pane>

          <nldd-split-view-pane slot="toolbar-medium" {...ONLY_MD}>
            <NarrowToolbar instanceName={instanceName} withName />
          </nldd-split-view-pane>

          <nldd-split-view-pane slot="toolbar-small" {...ONLY_SM}>
            <NarrowToolbar instanceName={instanceName} />
          </nldd-split-view-pane>

          <nldd-split-view-pane slot="main" has-content>
            <nldd-page landmarks="page" accessible-label={instanceName}>
              {/* The skip link lands here; tabIndex -1 lets it take focus without being a tab stop. */}
              <div id={MAIN_CONTENT_ID} tabIndex={-1}>
                <Outlet />
              </div>
            </nldd-page>
          </nldd-split-view-pane>
        </nldd-bar-split-view>
      </nldd-app-view>
    </>
  );
}
