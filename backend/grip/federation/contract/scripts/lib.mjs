// Shared helpers for the build and validation scripts.
import { readFileSync, readdirSync } from 'node:fs';
import { createHash } from 'node:crypto';

export const ROOT = new URL('..', import.meta.url).pathname;
export const readJson = (path) => JSON.parse(readFileSync(ROOT + path, 'utf8'));
export const listJson = (dir) => readdirSync(ROOT + dir).filter((f) => f.endsWith('.json')).sort();

// RFC 8785 canonical JSON. Sufficient here because the contract carries no floats.
export const canonicalize = (value) => {
  if (value === null || typeof value !== 'object') return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(canonicalize).join(',')}]`;
  const members = Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonicalize(value[key])}`);
  return `{${members.join(',')}}`;
};

export const sha256Hex = (text) => createHash('sha256').update(text).digest('hex');

export const loadSchemas = () =>
  Object.fromEntries(listJson('schemas').map((file) => [file.replace('.schema.json', ''), readJson(`schemas/${file}`)]));
