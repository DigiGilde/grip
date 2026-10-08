/**
 * Registers the nldd-* custom elements this app uses.
 *
 * Deliberately not `import '@nldd/design-system'`: that barrel pulls in every
 * component, including the code editors. The package ships a subpath export
 * per component, so we register only what we render.
 *
 * Adding a component? Add its import here, alphabetically within its group,
 * and rerun `npm run generate:nldd-types` so nldd-elements.d.ts drops its
 * NOT REGISTERED note. A tag used without an import renders its children
 * unstyled with no error.
 *
 * Elements that a parent module registers are left out: nldd-menu-item and
 * nldd-menu-group come with menu, nldd-toolbar-item and nldd-toolbar-title
 * with toolbar, nldd-tab-bar-item with tab-bar.
 */

// Layout
import '@nldd/design-system/app-view';
import '@nldd/design-system/bar-split-view';
import '@nldd/design-system/container';
import '@nldd/design-system/page';
import '@nldd/design-system/simple-section';
import '@nldd/design-system/split-view-pane';

// Actions
import '@nldd/design-system/button';
import '@nldd/design-system/icon-button';
import '@nldd/design-system/menu';
import '@nldd/design-system/toolbar';

// Content
import '@nldd/design-system/title';

// Navigation
import '@nldd/design-system/skip-link';
import '@nldd/design-system/tab-bar';

// Status and feedback
import '@nldd/design-system/banner';
import '@nldd/design-system/inline-dialog';
