// Builds a static reading page per service plus an index, into dist/.
import { execFileSync } from 'node:child_process';
import { mkdirSync, writeFileSync } from 'node:fs';
import { ROOT, readJson } from './lib.mjs';

const services = [
  { name: 'corpus-context', spec: 'corpus-context/v1/openapi.yaml' },
  { name: 'grip-opdrachtverkeer', spec: 'opdrachtverkeer/v1/openapi.yaml' },
];
mkdirSync(`${ROOT}dist`, { recursive: true });
for (const service of services) {
  execFileSync('npx', ['redocly', 'build-docs', service.spec, '--output', `dist/${service.name}.html`], { cwd: ROOT, stdio: 'inherit' });
  // The bundled contract as JSON, the form an implementation serves at /v1/openapi.json.
  execFileSync('npx', ['redocly', 'bundle', service.spec, '--ext', 'json', '--output', `dist/${service.name}.openapi.json`], { cwd: ROOT, stdio: 'inherit' });
}

const kern = readJson('vocabulaire/kern.json');
const escape = (text) => text.replace(/&/g, '&amp;').replace(/</g, '&lt;');
const rows = (types) => types.map((type) => `<tr><td><code>${type.id}</code></td><td>${escape(type.label_nl)}</td><td>${escape(type.omschrijving)}</td><td><code>${type.uri}</code></td></tr>`).join('\n');
const table = (types) => `<table><thead><tr><th>Id</th><th>Naam</th><th>Betekenis</th><th>URI</th></tr></thead><tbody>${rows(types)}</tbody></table>`;
const version = readJson('package.json').version;
writeFileSync(`${ROOT}dist/index.html`, `<!doctype html>
<html lang="nl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>grip-koppelvlakken ${version}</title>
<style>body{font:16px/1.5 system-ui,sans-serif;max-width:60rem;margin:2rem auto;padding:0 1rem}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccc;padding:.4rem .6rem;text-align:left;vertical-align:top}code{font-size:.9em}</style>
</head><body>
<h1>grip-koppelvlakken ${version}</h1>
<p>Contracten voor het verkeer tussen grip-instanties en corpus-systemen.</p>
<ul>
${services.map((service) => `<li><a href="${service.name}.html">${service.name}</a> (<a href="${service.name}.openapi.json">openapi.json</a>)</li>`).join('\n')}
</ul>
<h2>Node-typen</h2>
${table(kern.node_typen)}
<h2>Edge-typen</h2>
${table(kern.edge_typen)}
<p>De naamruimte <code>${kern.naamruimte}</code> is een plaatshouder.</p>
</body></html>
`);
console.log('wrote dist/index.html');
