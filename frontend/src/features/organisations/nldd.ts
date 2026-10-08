/**
 * Makes sure the nldd-* elements of this feature are registered, see
 * ./elements. Not in a test run: the design system's modules need a real
 * browser, and the render tests read the light DOM with the elements left
 * unregistered, as src/test/setup.ts describes.
 */
if (import.meta.env.MODE !== 'test') {
  void import('./elements');
}

export {};
