import { Outlet } from 'react-router-dom';
import { BrandMark } from '@/brand/BrandMark';
import { PRODUCT_NAME, instanceNames } from '@/brand/names';
import { TaskBar } from '@/features/tasks/TaskBar';
import { PATHS } from '@/paths';
import { AccountMenu, LogoutMenuItem } from './AccountMenu';
import {
  MainNavigation,
  MainNavigationOverflow,
  NavigationMenuButton,
  SectionViews,
} from './MainNavigation';
import { useInstance } from './useInstance';
import { useRouteFocus } from './useRouteFocus';
import { useAppBadge } from '@/features/notifications/useAppBadge';
import { useOnline } from '@/pwa/useOnline';
import './shell.css';

const MAIN_CONTENT_ID = 'inhoud';

// `above` and `only` are read off a pane by nldd-bar-split-view, which is why
// the package types them on the parent and not on nldd-split-view-pane. Spread
// as plain attributes until the package's types cover them.
const FROM_LG: object = { above: 'lg' };
const ONLY_MD: object = { only: 'md' };
const ONLY_SM: object = { only: 'sm' };

function capitalised(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/**
 * The start of the bar: the product as its mark, the organisation as the
 * name, one link to the start. A note about the environment, such as the
 * example data, is a tag beside the name and no part of it.
 */
function BrandTitle({ instanceName, markOnly }: { instanceName?: string; markOnly?: boolean }) {
  const { organisation, environment } = instanceNames(instanceName);
  const name = organisation || PRODUCT_NAME;
  if (markOnly) {
    // On a phone there is no room for the name: the mark stands alone, is
    // still the way to the start, and carries the name for a screen reader.
    return (
      <nldd-toolbar-title slot="start" href={PATHS.statusOverview} min-width="0">
        <BrandMark slot="media" size={24} label={`${name}, naar de start`} />
      </nldd-toolbar-title>
    );
  }
  return (
    <nldd-toolbar-title slot="start" text={name} href={PATHS.statusOverview}>
      <BrandMark slot="media" size={24} />
      {environment && <nldd-tag slot="action" size="sm" text={capitalised(environment)} />}
    </nldd-toolbar-title>
  );
}

/**
 * The bar below the widest breakpoint: the sections behind one menu button
 * that names the section you are in, and the account as an icon. The name of
 * the instance stands beside it while there is room, and goes on a phone.
 */
function NarrowToolbar({
  instanceName,
  rawName,
  withName,
}: {
  instanceName: string;
  rawName?: string;
  withName?: boolean;
}) {
  return (
    <nldd-container padding="8">
      <nldd-toolbar label={instanceName}>
        <nldd-toolbar-item slot="start" priority={3}>
          <NavigationMenuButton />
          <MainNavigationOverflow />
        </nldd-toolbar-item>
        <BrandTitle instanceName={rawName} markOnly={!withName} />
        <nldd-toolbar-item slot="end" priority={2}>
          <AccountMenu placement="bottom-end" compact />
          <LogoutMenuItem slot="overflow" />
        </nldd-toolbar-item>
      </nldd-toolbar>
    </nldd-container>
  );
}

/** Said once, at the top, while the browser has no connection. */
function OfflineNotice() {
  const online = useOnline();
  if (online) return null;
  return (
    <nldd-container padding="16">
      <nldd-banner
        variant="warning"
        size="sm"
        text="Geen verbinding"
        supporting-text="Grip heeft een internetverbinding nodig. Wat je ziet kan verouderd zijn en opslaan lukt niet."
      />
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
  useAppBadge();

  const { organisation } = instanceNames(instance?.name);
  const instanceName = organisation ? `${organisation}, ${PRODUCT_NAME}` : PRODUCT_NAME;

  return (
    <>
      <nldd-skip-link href={`#${MAIN_CONTENT_ID}`} text="Direct naar de inhoud" />
      <nldd-app-view>
        <nldd-bar-split-view>
          <nldd-split-view-pane slot="toolbar-wide" {...FROM_LG}>
            <nldd-container padding="8">
              <nldd-toolbar label={instanceName}>
                <BrandTitle instanceName={instance?.name} />
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
            <NarrowToolbar instanceName={instanceName} rawName={instance?.name} withName />
          </nldd-split-view-pane>

          <nldd-split-view-pane slot="toolbar-small" {...ONLY_SM}>
            <NarrowToolbar instanceName={instanceName} />
          </nldd-split-view-pane>

          <nldd-split-view-pane slot="main" has-content>
            <nldd-page landmarks="page" accessible-label={instanceName}>
              {/* The skip link lands here; tabIndex -1 lets it take focus without being a tab stop. */}
              <div id={MAIN_CONTENT_ID} tabIndex={-1}>
                {/* The task this page was opened for, when the address names one. */}
                {/* The sibling pages of the section you are in; nothing for a section of one page. */}
                <SectionViews />
                <TaskBar />
                <OfflineNotice />
                <Outlet />
              </div>
            </nldd-page>
          </nldd-split-view-pane>
        </nldd-bar-split-view>
      </nldd-app-view>
    </>
  );
}
