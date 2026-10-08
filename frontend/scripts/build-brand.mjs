/**
 * Builds the icon set of grip from the one source drawing, brand/mark.svg.
 *
 * Nothing in public/ or docs/merk/ that this script writes is edited by hand:
 * change the drawing or the numbers below and run `just brand`. The results
 * are committed, so building the frontend does not need the tools used here.
 *
 * Needs rsvg-convert (librsvg) and magick (ImageMagick) on the PATH.
 */
import { execFileSync } from 'node:child_process';
import { mkdirSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';

const root = path.resolve(import.meta.dirname, '..');
const brandDir = path.join(root, 'brand');
const publicDir = path.join(root, 'public');
const iconsDir = path.join(publicDir, 'icons');
const docsDir = path.resolve(root, '../docs/merk');

// The reference value of the token lintblauw and the step that pairs with it
// on a dark surface (lintblauw-750 in dark mode). Static files cannot read the
// design system's tokens, so the two values are repeated here and only here.
const LINTBLAUW = '#154273';
const LINTBLAUW_ON_DARK = '#85b5ee';
const WHITE = '#ffffff';
const DARK_SURFACE = '#20242d';

/** The paths of a drawing, without its svg wrapper. */
function shapes(file) {
  const svg = readFileSync(file, 'utf8').replace(/<!--[\s\S]*?-->/g, '');
  return svg
    .replace(/^[\s\S]*?<svg[^>]*>/, '')
    .replace(/<\/svg>\s*$/, '')
    .trim();
}

/** Attributes of the root element that the shapes rely on (fill or stroke). */
function paint(file) {
  const tag = readFileSync(file, 'utf8').match(/<svg[^>]*>/)[0];
  return [...tag.matchAll(/\s(fill|stroke|stroke-width)="([^"]*)"/g)]
    .map(([, name, value]) => `${name}="${value}"`)
    .join(' ');
}

/** A drawing placed as a nested svg: position, size and colour. */
function place(file, x, y, size, color) {
  return `<svg x="${x}" y="${y}" width="${size}" height="${size}" viewBox="0 0 48 48" color="${color}" ${paint(file)}>${shapes(file)}</svg>`;
}

/** A square tile in lintblauw with the mark in white; `share` is the mark's part of the side. */
function tile(file, side, share, radius = 0) {
  const size = side * share;
  const offset = (side - size) / 2;
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${side}" height="${side}" viewBox="0 0 ${side} ${side}"><rect width="${side}" height="${side}" rx="${radius}" fill="${LINTBLAUW}"/>${place(file, offset, offset, size, WHITE)}</svg>`;
}

function png(svg, target, side) {
  execFileSync('rsvg-convert', ['-w', String(side), '-h', String(side), '-o', target], {
    input: svg,
  });
}

function need(tool) {
  try {
    execFileSync(tool, ['--version'], { stdio: 'ignore' });
  } catch {
    console.error(`${tool} ontbreekt. Installeer librsvg en ImageMagick en probeer opnieuw.`);
    process.exit(1);
  }
}

need('rsvg-convert');
need('magick');
for (const dir of [publicDir, iconsDir, docsDir]) mkdirSync(dir, { recursive: true });

const mark = path.join(brandDir, 'mark.svg');
const markShapes = shapes(mark);

// The favicon follows the colour scheme of the browser: a tab strip is light
// or dark, and one fixed blue is too faint on one of the two.
writeFileSync(
  path.join(publicDir, 'favicon.svg'),
  `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48"><style>path{fill:${LINTBLAUW}}@media (prefers-color-scheme:dark){path{fill:${LINTBLAUW_ON_DARK}}}</style>${markShapes}</svg>\n`,
);

// One colour, for places that tint an icon themselves.
writeFileSync(
  path.join(iconsDir, 'icon-mono.svg'),
  `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48" fill="#000000">${markShapes}</svg>\n`,
);
png(
  `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48" fill="#000000">${markShapes}</svg>`,
  path.join(iconsDir, 'icon-mono-512.png'),
  512,
);

// Browsers without svg favicons get a tile: it holds on any tab colour.
const icoParts = [16, 32, 48].map((side) => {
  const target = path.join(iconsDir, `.favicon-${side}.png`);
  png(tile(mark, 48, 0.84, 6), target, side);
  return target;
});
execFileSync('magick', [...icoParts, path.join(publicDir, 'favicon.ico')]);
execFileSync('rm', icoParts);

// Home screen icons. The platform rounds the corners; the tile is full bleed.
png(tile(mark, 180, 0.6), path.join(publicDir, 'apple-touch-icon.png'), 180);
png(tile(mark, 512, 0.62, 96), path.join(iconsDir, 'icon-192.png'), 192);
png(tile(mark, 512, 0.62, 96), path.join(iconsDir, 'icon-512.png'), 512);
// Maskable: everything that matters stays inside the inner 80 percent circle.
png(tile(mark, 512, 0.46), path.join(iconsDir, 'icon-maskable-512.png'), 512);
png(tile(mark, 512, 0.46), path.join(iconsDir, 'icon-maskable-192.png'), 192);

// The mark with the product name, for the README and link previews.
writeFileSync(
  path.join(docsDir, 'grip.svg'),
  `<svg xmlns="http://www.w3.org/2000/svg" width="640" height="240" viewBox="0 0 640 240"><rect width="640" height="240" fill="${WHITE}"/>${place(mark, 150, 60, 120, LINTBLAUW)}<text x="298" y="163" font-family="Verdana, sans-serif" font-size="112" font-weight="700" letter-spacing="-3" fill="${LINTBLAUW}">grip</text></svg>\n`,
);
execFileSync('rsvg-convert', [
  '-w',
  '1280',
  '-o',
  path.join(docsDir, 'grip.png'),
  path.join(docsDir, 'grip.svg'),
]);

// The sheet with every direction that was drawn, for whoever wants to choose
// differently: each at 16, 32, 64 and 180, on light and dark, and as an icon.
const directions = readdirSync(path.join(brandDir, 'richtingen'))
  .filter((name) => name.endsWith('.svg'))
  .sort();
const rowHeight = 230;
const sizes = [16, 32, 64, 180];
const rows = directions.map((name, row) => {
  const file = path.join(brandDir, 'richtingen', name);
  const y = row * rowHeight + 30;
  let x = 20;
  const parts = [
    `<text x="20" y="${y - 8}" font-family="Verdana, sans-serif" font-size="13" fill="#333">${name.replace('.svg', '')}</text>`,
  ];
  for (const size of sizes) {
    parts.push(place(file, x, y, size, LINTBLAUW));
    x += size + 16;
  }
  parts.push(`<rect x="${x}" y="${y - 10}" width="344" height="200" fill="${DARK_SURFACE}"/>`);
  x += 12;
  for (const size of sizes) {
    parts.push(place(file, x, y, size, LINTBLAUW_ON_DARK));
    x += size + 16;
  }
  x += 24;
  for (const side of [180, 64, 32, 16]) {
    const inner = side * 0.62;
    const offset = (side - inner) / 2;
    parts.push(
      `<rect x="${x}" y="${y}" width="${side}" height="${side}" rx="${side * 0.19}" fill="${LINTBLAUW}"/>`,
      place(file, x + offset, y + offset, inner, WHITE),
    );
    x += side + 16;
  }
  const inner = 180 * 0.46;
  const offset = (180 - inner) / 2;
  parts.push(
    `<circle cx="${x + 90}" cy="${y + 90}" r="90" fill="${LINTBLAUW}"/>`,
    place(file, x + offset, y + offset, inner, WHITE),
  );
  return parts.join('');
});
const sheetWidth = 1330;
const sheetHeight = directions.length * rowHeight + 20;
const sheet = `<svg xmlns="http://www.w3.org/2000/svg" width="${sheetWidth}" height="${sheetHeight}" viewBox="0 0 ${sheetWidth} ${sheetHeight}"><rect width="${sheetWidth}" height="${sheetHeight}" fill="${WHITE}"/>${rows.join('')}</svg>`;
execFileSync('rsvg-convert', ['-o', path.join(docsDir, 'richtingen.png')], { input: sheet });

console.log('Merkbestanden bijgewerkt in public/ en docs/merk/.');
