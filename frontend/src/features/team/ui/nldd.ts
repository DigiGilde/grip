/**
 * Makes sure the nldd-* elements of the rates, team and costs screens are
 * registered, see ./elements.
 *
 * Not in a test run: the design system's modules need a real browser
 * (matchMedia, among others), and the render tests read the light DOM these
 * screens are responsible for, with the elements left unregistered, exactly
 * as src/test/setup.ts describes.
 */
if (import.meta.env.MODE !== 'test') {
  void import('./elements');
}

export {};
