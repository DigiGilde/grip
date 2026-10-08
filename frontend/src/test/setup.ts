import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

// The nldd-* elements are deliberately not registered in tests: they stay
// unknown elements, so a test reads the light DOM this app is responsible for.
afterEach(() => {
  cleanup();
  document.title = '';
});
