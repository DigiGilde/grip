/**
 * Makes sure the nldd-* elements of the quote, signing and monthly close
 * screens are registered, see ./elements.
 *
 * Not in a test run: the design system's modules need a real browser, and
 * the render tests read the light DOM these screens are responsible for,
 * with the elements left unregistered, as src/test/setup.ts describes.
 * Elements upgrade whenever their definition arrives, so loading it after
 * the first render is fine.
 */
if (import.meta.env.MODE !== 'test') {
  void import('./elements');
}

export {};
