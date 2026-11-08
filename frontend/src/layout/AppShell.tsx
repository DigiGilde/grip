import { useEffect, useRef, type ReactNode } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { BrandMark } from '@/brand/BrandMark';
import { PRODUCT_NAME, instanceNames } from '@/brand/names';
import { SearchField } from '@/features/search/SearchField';
import { TaskBar } from '@/features/tasks/TaskBar';
import { PageBoundary } from '@/PageBoundary';
import { preloadFor } from '@/pageChunks';
import { PATHS } from '@/paths';
import { iconOf } from '@/ui/icons';
import { useNarrow } from '@/ui/layout';
import { AccountMenu } from './AccountMenu';
import { BottomNavigation, MainNavigation, SettingsNavigation } from './MainNavigation';
import { ExampleNotice } from './ExampleMode';
import { useInstance } from './useInstance';
import { useRouteFocus } from './useRouteFocus';
import { internalHref, useRouterLinks } from './useRouterLinks';
import { useAppBadge } from '@/features/notifications/useAppBadge';
import { useOnline } from '@/pwa/useOnline';

const MAIN_CONTENT_ID = 'inhoud';
/** The name of the landmark around the application bar. */
const BAR_LABEL = 'Navigatie en account';

// `above` and `only` are read off a pane by nldd-bar-split-view, which is why
// the package types them on the parent and not on nldd-split-view-pane. Spread
// as plain attributes until the package's types cover them.
const FROM_MD: object = { above: 'md' };
const ONLY_SM: object = { only: 'sm' };

const NO_ROOM_FOR_NAME = '(max-width: 1199px)';

function capitalised(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/**
 * The start of the bar: the product as its mark, the organisation as the
 * name, one link to the start. A note about the environment, such as the
 * example data, is a tag beside the name and no part of it. A toolbar title
 * has no priority and moves items to the menu before it narrows, so where the
 * name would cost the search field or the account only the mark stays.
 */
function BrandTitle({ instanceName }: { instanceName?: string }) {
  const instance = useInstance();
  const markOnly = useNarrow(NO_ROOM_FOR_NAME);
  const named = instanceNames(instanceName);
  const organisation = named.organisation;
  // The mode of the instance decides, not what its name happens to say.
  const environment = instance?.example ? 'voorbeeld' : named.environment;
  const name = organisation || PRODUCT_NAME;
  if (markOnly) {
    return (
      <nldd-toolbar-title slot="start" href={PATHS.start}>
        <BrandMark slot="media" size={24} label={`${name}, naar de start`} />
      </nldd-toolbar-title>
    );
  }
  return (
    <nldd-toolbar-title slot="start" text={name} href={PATHS.start}>
      <BrandMark slot="media" size={24} />
      {environment && <nldd-tag slot="action" size="sm" text={capitalised(environment)} />}
    </nldd-toolbar-title>
  );
}

/** A bar of the shell: a named region, with every link in it handed to the router. */
function Bar({ children }: { children: ReactNode }) {
  const ref = useRef<HTMLElement>(null);
  useRouterLinks(ref);
  return (
    // A named region, so the bar sits inside a landmark. Not a header:
    // nldd-page already renders the banner of the document, and a second one
    // is announced twice.
    <section ref={ref} aria-label={BAR_LABEL}>
      <nldd-container padding="8">{children}</nldd-container>
    </section>
  );
}

/**
 * Fetches the page behind a link as soon as the pointer or the focus is on
 * it, so it is there when the click comes. One listener for every link of
 * the application; a link to the page that is already loaded costs nothing.
 */
function usePreloadOnIntent(): void {
  useEffect(() => {
    const onIntent = (event: Event) => {
      const href = internalHref(event);
      if (href !== null) preloadFor(href);
    };
    document.addEventListener('pointerover', onIntent, { passive: true });
    document.addEventListener('focusin', onIntent);
    return () => {
      document.removeEventListener('pointerover', onIntent);
      document.removeEventListener('focusin', onIntent);
    };
  }, []);
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
 * The top bar reads from left to right as: where you are (the organisation's
 * grip, a link to the start), the places, the search field, and at the end what
 * is not daily work: the settings of the instance and who you are. On a small
 * screen there is no top bar: the places stand at the bottom, within reach of a
 * thumb, as icons with their word, and the account is the place Ik.
 */
export function AppShell() {
  const instance = useInstance();
  const { pathname } = useLocation();
  useRouteFocus();
  useAppBadge();
  usePreloadOnIntent();

  const { organisation } = instanceNames(instance?.name);
  const instanceName = organisation ? `${organisation}, ${PRODUCT_NAME}` : PRODUCT_NAME;

  return (
    <>
      <nldd-skip-link href={`#${MAIN_CONTENT_ID}`} text="Direct naar de inhoud" />
      <nldd-shell>
        <nldd-bar-split-view>
          <nldd-split-view-pane slot="toolbar" {...FROM_MD}>
            <Bar>
              <nldd-toolbar accessible-label={instanceName}>
                <BrandTitle instanceName={instance?.name} />
                <MainNavigation />
                <nldd-toolbar-item
                  slot="center"
                  min-width="240px"
                  width="33%"
                  max-width="480px"
                  priority={3}
                >
                  <SearchField />
                  <nldd-menu-item
                    slot="overflow"
                    icon={iconOf('search')}
                    text="Zoek op naam"
                    href={PATHS.search}
                  />
                </nldd-toolbar-item>
                <SettingsNavigation />
                <nldd-toolbar-item slot="end" priority={2}>
                  <AccountMenu placement="bottom-end" />
                  <nldd-menu-item
                    slot="overflow"
                    icon={iconOf('account')}
                    text="Ik"
                    href={PATHS.me}
                  />
                </nldd-toolbar-item>
              </nldd-toolbar>
            </Bar>
          </nldd-split-view-pane>

          <nldd-split-view-pane slot="main" has-content>
            <nldd-page landmarks="page" accessible-label={instanceName}>
              {/* The skip link lands here; tabIndex -1 lets it take focus without being a tab stop. */}
              <div id={MAIN_CONTENT_ID} tabIndex={-1}>
                {/* The task this page was opened for, when the address names one. */}
                <ExampleNotice />
                <TaskBar />
                <OfflineNotice />
                <PageBoundary resetKey={pathname}>
                  <Outlet />
                </PageBoundary>
              </div>
            </nldd-page>
          </nldd-split-view-pane>

          <nldd-split-view-pane slot="toolbar-sm" {...ONLY_SM}>
            <Bar>
              <nldd-toolbar size="lg" accessible-label={instanceName}>
                <BottomNavigation />
              </nldd-toolbar>
            </Bar>
          </nldd-split-view-pane>
        </nldd-bar-split-view>
      </nldd-shell>
    </>
  );
}
