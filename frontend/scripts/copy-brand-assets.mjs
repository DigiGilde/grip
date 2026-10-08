/**
 * Copies the favicon and touch icon out of @nldd/design-system into public/.
 *
 * The files stay in the package rather than in this repository, so the
 * package's NOTICES.md remains the one place for the terms of use.
 */
import { copyFileSync, mkdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const publicDir = path.resolve(import.meta.dirname, '../public');
mkdirSync(publicDir, { recursive: true });

for (const asset of ['favicon.svg', 'touch-icon.png']) {
  const source = fileURLToPath(import.meta.resolve(`@nldd/design-system/${asset}`));
  copyFileSync(source, path.join(publicDir, asset));
}
