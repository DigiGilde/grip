// Validates the examples against the schemas, and the invariants that JSON Schema cannot express.
import Ajv2020 from 'ajv/dist/2020.js';
import addFormats from 'ajv-formats';
import { verify, createPublicKey } from 'node:crypto';
import { readJson, listJson, loadSchemas, canonicalize, sha256Hex } from './lib.mjs';

const BASE = 'https://schemas.local/';
const ajv = new Ajv2020({ allErrors: true, strict: true, strictTypes: false, strictRequired: false });
addFormats(ajv);
const schemas = loadSchemas();
for (const [name, schema] of Object.entries(schemas)) ajv.addSchema({ ...schema, $id: `${BASE}${name}.schema.json` });

const failures = [];
const fail = (message) => failures.push(message);
const schemaOf = (file) => file.split('.')[0];
const validatorFor = (name) => ajv.getSchema(`${BASE}${name}.schema.json`);

const covered = new Set();
for (const file of listJson('examples/valid')) {
  const validate = validatorFor(schemaOf(file));
  if (!validate) { fail(`examples/valid/${file}: no schema named ${schemaOf(file)}`); continue; }
  covered.add(schemaOf(file));
  if (!validate(readJson(`examples/valid/${file}`))) fail(`examples/valid/${file}: ${ajv.errorsText(validate.errors)}`);
}
for (const file of listJson('examples/invalid')) {
  const validate = validatorFor(schemaOf(file));
  if (!validate) { fail(`examples/invalid/${file}: no schema named ${schemaOf(file)}`); continue; }
  if (validate(readJson(`examples/invalid/${file}`))) fail(`examples/invalid/${file}: expected to be rejected, but it is valid`);
}
for (const name of Object.keys(schemas)) {
  if (name !== 'vocabulary' && !covered.has(name)) fail(`schemas/${name}.schema.json: no valid example`);
}

// The generated core vocabulary follows the vocabulary schema and matches the enums in node and edge.
const kern = readJson('vocabulaire/kern.json');
const validateVocabulary = validatorFor('vocabulary');
if (!validateVocabulary(kern)) fail(`vocabulaire/kern.json: ${ajv.errorsText(validateVocabulary.errors)}`);
const sameSet = (a, b) => a.length === b.length && a.every((item) => b.includes(item));
const coreEnum = (schema) => schema.properties.type.anyOf.find((option) => option.enum).enum;
if (!sameSet(coreEnum(schemas.node), kern.node_types.map((type) => type.id))) fail('node.schema.json: type enum differs from the core node types');
if (!sameSet(coreEnum(schemas.edge), kern.edge_types.map((type) => type.id))) fail('edge.schema.json: type enum differs from the core edge types');

// A quote hash is the SHA-256 of the canonical snapshot.
for (const file of listJson('examples/valid').filter((name) => schemaOf(name) === 'quote')) {
  const quote = readJson(`examples/valid/${file}`);
  if (sha256Hex(canonicalize(quote.snapshot)) !== quote.snapshot_hash) fail(`examples/valid/${file}: snapshot_hash does not match the snapshot`);
}

// An acceptance JWS verifies against the example key set and signs exactly the acceptance fields.
const SIGNED_FIELDS = ['id', 'quote_id', 'quote_hash', 'signer', 'organisation', 'signed_at', 'form'];
const jwks = readJson('examples/valid/jwks.json');
for (const file of listJson('examples/valid').filter((name) => schemaOf(name) === 'acceptance')) {
  const acceptance = readJson(`examples/valid/${file}`);
  if (!acceptance.jws) continue;
  const [header, payload, signature] = acceptance.jws.split('.');
  const { alg, kid } = JSON.parse(Buffer.from(header, 'base64url'));
  const jwk = jwks.keys.find((key) => key.kid === kid);
  if (alg !== 'ES256' || !jwk) { fail(`examples/valid/${file}: JWS header must use ES256 and a kid from examples/valid/jwks.json`); continue; }
  const verified = verify('sha256', Buffer.from(`${header}.${payload}`), { key: createPublicKey({ key: jwk, format: 'jwk' }), dsaEncoding: 'ieee-p1363' }, Buffer.from(signature, 'base64url'));
  if (!verified) fail(`examples/valid/${file}: JWS signature does not verify`);
  const expected = canonicalize(Object.fromEntries(SIGNED_FIELDS.map((field) => [field, acceptance[field]])));
  if (Buffer.from(payload, 'base64url').toString() !== expected) fail(`examples/valid/${file}: JWS payload differs from the acceptance fields`);
}

if (failures.length) {
  console.error(failures.join('\n'));
  console.error(`\n${failures.length} problem(s)`);
  process.exit(1);
}
console.log(`ok: ${Object.keys(schemas).length} schemas, ${listJson('examples/valid').length} valid and ${listJson('examples/invalid').length} invalid examples`);
