import { Outlet } from 'react-router-dom';
import { PATHS } from '@/paths';
import { AccountMenu, LogoutMenuItem } from './AccountMenu';
import { MainNavigation, MainNavigationOverflow } from './MainNavigation';
import { useInstance } from './useInstance';
import { useRouteFocus } from './useRouteFocus';

const MAIN_CONTENT_ID = 'inhoud';

// `above` and `only` are read off a pane by nldd-bar-split-view, which is why
// the package types them on the parent and not on nldd-split-view-pane. Spread
// as plain attributes until the package's types cover them.
const FROM_MD: object = { above: 'md' };
const ONLY_SM: object = { only: 'sm' };

/**
 * The application shell: a main toolbar around one content pane.
 *
 * Follows the design system's application pattern. The toolbar sits in its own
 * bar of the bar split view rather than in the pane, so it belongs to the whole
 * screen and does not scroll with the content. On small screens a second
 * toolbar takes its place at the bottom, within reach of a thumb, with the
 * sections as icons with a label.
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
          <nldd-split-view-pane slot="toolbar-top" {...FROM_MD}>
            <nldd-container padding="8">
              <nldd-toolbar label={instanceName}>
                <nldd-toolbar-title
                  slot="start"
                  text={instanceName}
                  href={PATHS.statusOverview}
                />
                <nldd-toolbar-item slot="start" priority={2}>
                  <MainNavigation />
                  <MainNavigationOverflow />
                </nldd-toolbar-item>
                <nldd-toolbar-item slot="end" priority={1}>
                  <AccountMenu placement="bottom-end" />
                  <LogoutMenuItem slot="overflow" />
                </nldd-toolbar-item>
              </nldd-toolbar>
            </nldd-container>
          </nldd-split-view-pane>

          <nldd-split-view-pane slot="main" has-content>
            <nldd-page landmarks="page" accessible-label={instanceName}>
              {/* The skip link lands here; tabIndex -1 lets it take focus without being a tab stop. */}
              <div id={MAIN_CONTENT_ID} tabIndex={-1}>
                <Outlet />
              </div>
            </nldd-page>
          </nldd-split-view-pane>

          <nldd-split-view-pane slot="toolbar-bottom" {...ONLY_SM}>
            <nldd-container padding="8">
              <nldd-toolbar size="lg" label={instanceName}>
                <nldd-toolbar-item slot="start" priority={2}>
                  <MainNavigation withIcons />
                  <MainNavigationOverflow />
                </nldd-toolbar-item>
                <nldd-toolbar-item slot="end" priority={1}>
                  <AccountMenu placement="top-end" />
                  <LogoutMenuItem slot="overflow" />
                </nldd-toolbar-item>
              </nldd-toolbar>
            </nldd-container>
          </nldd-split-view-pane>
        </nldd-bar-split-view>
      </nldd-app-view>
    </>
  );
}
