// Compares the OpenAPI document an implementation generates with a contract in this repo.
// Usage: node scripts/compare-openapi.mjs <contract.openapi.json> <implementation-openapi.json> [path-prefix]
// The contract is the bundled JSON from dist/ (just docs). The optional prefix (for example /v1)
// is stripped from the implementation's paths when it declares the version in the path.
import { readFileSync } from 'node:fs';

const [contractPath, implementationPath, prefix = ''] = process.argv.slice(2);
if (!contractPath || !implementationPath) {
  console.error('Usage: node scripts/compare-openapi.mjs <contract.openapi.json> <implementation-openapi.json> [path-prefix]');
  process.exit(2);
}
const contract = JSON.parse(readFileSync(contractPath, 'utf8'));
const implementation = JSON.parse(readFileSync(implementationPath, 'utf8'));
const METHODS = ['get', 'put', 'post', 'delete', 'patch'];
const normalize = (path) => path.replace(/\{[^}]+\}/g, '{}');
const resolve = (document, item) => (item?.$ref ? item.$ref.replace('#/', '').split('/').reduce((node, key) => node?.[key], document) : item);
const implemented = new Map();
for (const [path, item] of Object.entries(implementation.paths ?? {})) {
  const stripped = prefix && path.startsWith(prefix) ? path.slice(prefix.length) : path;
  implemented.set(normalize(stripped), item);
}

const problems = [];
for (const [path, item] of Object.entries(contract.paths)) {
  const other = implemented.get(normalize(path));
  for (const method of METHODS.filter((name) => item[name])) {
    const label = `${method.toUpperCase()} ${path}`;
    const operation = other?.[method];
    if (!operation) { problems.push(`${label}: missing`); continue; }
    const names = (document, source) => (source.parameters ?? []).map((parameter) => resolve(document, parameter)).filter((parameter) => parameter.in === 'query').map((parameter) => parameter.name);
    const offered = names(implementation, operation);
    for (const name of names(contract, item[method])) {
      if (!offered.includes(name)) problems.push(`${label}: query parameter ${name} missing`);
    }
    for (const status of Object.keys(item[method].responses).filter((code) => code.startsWith('2'))) {
      if (!operation.responses?.[status]) problems.push(`${label}: response ${status} missing`);
    }
  }
}
if (problems.length) {
  console.error(problems.join('\n'));
  console.error(`\n${problems.length} difference(s) with the contract`);
  process.exit(1);
}
console.log('ok: every operation, query parameter and success response of the contract is present');
