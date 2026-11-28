// Generates vocabulaire/kern.json, vocabulaire/README.md and context.jsonld from
// vocabulaire/kern.source.json and the property names used in schemas/.
// With --check it fails when a generated file is out of date.
import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { ROOT, readJson, loadSchemas } from './lib.mjs';

const source = readJson('vocabulaire/kern.source.json');
const base = source.naamruimte;
const def = `${base}def/`;
const expand = (kind, type) => ({ id: type.id, uri: `${def}${kind}/${type.id}`, label_nl: type.label_nl, omschrijving: type.omschrijving, eigen: false });
const nodeTypes = source.node_typen.map((type) => expand('node-type', type));
const edgeTypes = source.edge_typen.map((type) => expand('edge-type', type));

const kern = { naamruimte: def, node_typen: nodeTypes, edge_typen: edgeTypes };

const isUri = (schema) =>
  schema?.format === 'uri' || schema?.items?.format === 'uri' || (schema?.anyOf ?? []).some((option) => option.format === 'uri');
const properties = new Map();
const walk = (schema) => {
  if (!schema || typeof schema !== 'object') return;
  if (Array.isArray(schema)) return schema.forEach(walk);
  for (const [name, property] of Object.entries(schema.properties ?? {})) {
    properties.set(name, (properties.get(name) ?? false) || isUri(property));
  }
  Object.values(schema).forEach(walk);
};
Object.values(loadSchemas()).forEach(walk);

const typeIds = [...nodeTypes, ...edgeTypes].map((type) => type.id);
const duplicates = typeIds.filter((id, index) => typeIds.indexOf(id) !== index);
const collisions = typeIds.filter((id) => properties.has(id));
if (duplicates.length || collisions.length) {
  console.error('Type ids must be unique and must not equal a property name:', [...duplicates, ...collisions]);
  process.exit(1);
}

const terms = { '@version': 1.1, kv: def, uri: '@id', type: '@type' };
for (const name of [...properties.keys()].sort()) {
  if (name === 'uri' || name === 'type') continue;
  terms[name] = properties.get(name) ? { '@id': `kv:${name}`, '@type': '@id' } : `kv:${name}`;
}
for (const type of nodeTypes) terms[type.id] = `kv:node-type/${type.id}`;
for (const type of edgeTypes) terms[type.id] = `kv:edge-type/${type.id}`;

const row = (type) => `| \`${type.id}\` | ${type.label_nl} | ${type.omschrijving} | ${type.uri} |`;
const table = (types) => ['| Id | Naam | Betekenis | URI |', '|---|---|---|---|', ...types.map(row)].join('\n');
const readme = `# Woordenlijst

Gegenereerd uit \`kern.source.json\` met \`just build\`. Niet met de hand bewerken.

> **Naamruimte is een plaatshouder.** \`${base}\` staat op een plek, in \`kern.source.json\`,
> en moet worden vervangen door een duurzaam domein voordat versie 1.0.0 wordt vastgesteld.

## Node-typen

${table(nodeTypes)}

## Edge-typen

${table(edgeTypes)}

## Eigen typen

Een corpus mag typen gebruiken die niet in de kernlijst staan. Daarvoor geldt:

1. Een eigen type staat in een naamruimte van het corpus zelf, bijvoorbeeld
   \`{corpus}/def/node-type/{id}\` of \`{corpus}/def/edge-type/{id}\`. Nooit in de naamruimte van de kernlijst.
2. In een bericht staat een kerntype als kort id (\`doel\`) en een eigen type als volledige URI.
3. Het corpus beschrijft zijn eigen typen via \`GET /woordenlijst\` van de dienst \`corpus-context\`, met \`eigen: true\`.
4. Een ontvanger die een eigen type niet kent, toont de node of edge met het type als URI en verwerkt de rest gewoon.
5. Een eigen type dat in meerdere corpora nodig blijkt, wordt voorgesteld voor de kernlijst (zie CONTRIBUTING.md).

De ids in de kernlijst komen overeen met de node-typen en edge-typen die Bouwmeester standaard kent.
De omschrijvingen van de node-typen zijn een eerste voorstel en moeten met de beheerders van het corpus worden vastgesteld.
`;

const outputs = {
  'vocabulaire/kern.json': JSON.stringify(kern, null, 2) + '\n',
  'vocabulaire/README.md': readme,
  'context.jsonld': JSON.stringify({ '@context': terms }, null, 2) + '\n',
};
const check = process.argv.includes('--check');
let stale = false;
for (const [path, content] of Object.entries(outputs)) {
  if (check) {
    if (!existsSync(ROOT + path) || readFileSync(ROOT + path, 'utf8') !== content) {
      console.error(`Out of date: ${path}. Run: just build`);
      stale = true;
    }
  } else {
    writeFileSync(ROOT + path, content);
    console.log(`wrote ${path}`);
  }
}
process.exit(stale ? 1 : 0);
