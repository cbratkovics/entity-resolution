#!/usr/bin/env node
/**
 * Copy the lab export into public/data/ for the static app.
 *
 * Source: <repo>/artifacts/lab/ (override with LAB_DATA_DIR, e.g. a mock set for e2e runs);
 * every *.json and *.csv.gz under it is copied preserving the relative layout, plus the sandbox
 * fixture apps/decision-lab/fixtures/synthetic_sandbox.json (or, when that is absent, the
 * fixture named by LAB_SANDBOX_FIXTURE, or <LAB_DATA_DIR>/synthetic_sandbox.json for mock sets).
 *
 * The script fails loudly when manifest.json is missing and never fabricates data.
 */
import { copyFileSync, existsSync, mkdirSync, readdirSync, rmSync, statSync } from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const appDir = resolve(here, '..');
const repoRoot = resolve(appDir, '..', '..');
const source = process.env.LAB_DATA_DIR ? resolve(process.env.LAB_DATA_DIR) : join(repoRoot, 'artifacts', 'lab');
const target = join(appDir, 'public', 'data');

function fail(message) {
  console.error(`sync-data: ${message}`);
  process.exit(1);
}

if (!existsSync(join(source, 'manifest.json'))) {
  fail(
    `${join(source, 'manifest.json')} is missing. The lab export has not been produced (run the Python exporter ` +
      `to write artifacts/lab/), or point LAB_DATA_DIR at a directory that contains it (for example a mock set from ` +
      `\`npm run mock-data -- <dir>\`). Nothing was copied and nothing is fabricated.`,
  );
}

function walk(dir) {
  const out = [];
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    const st = statSync(p);
    if (st.isDirectory()) out.push(...walk(p));
    else if (/\.json$/.test(name) || /\.csv\.gz$/.test(name)) out.push(p);
  }
  return out;
}

rmSync(target, { recursive: true, force: true });
mkdirSync(target, { recursive: true });
const copied = [];
for (const file of walk(source)) {
  const rel = relative(source, file);
  const dest = join(target, rel);
  mkdirSync(dirname(dest), { recursive: true });
  copyFileSync(file, dest);
  copied.push(rel);
}

const fixture = join(appDir, 'fixtures', 'synthetic_sandbox.json');
const fixtureOverride = process.env.LAB_SANDBOX_FIXTURE ? resolve(process.env.LAB_SANDBOX_FIXTURE) : null;
const sandboxDest = join(target, 'synthetic_sandbox.json');
if (existsSync(fixture)) {
  copyFileSync(fixture, sandboxDest);
  const i = copied.indexOf('synthetic_sandbox.json');
  if (i !== -1) copied.splice(i, 1);
  copied.push('synthetic_sandbox.json (fixtures/synthetic_sandbox.json)');
} else if (fixtureOverride && existsSync(fixtureOverride)) {
  copyFileSync(fixtureOverride, sandboxDest);
  copied.push(`synthetic_sandbox.json (LAB_SANDBOX_FIXTURE=${fixtureOverride})`);
} else if (copied.includes('synthetic_sandbox.json')) {
  console.warn('sync-data: WARNING: using the synthetic_sandbox.json found in the data directory (mock set); fixtures/synthetic_sandbox.json is absent.');
} else {
  console.warn('sync-data: WARNING: fixtures/synthetic_sandbox.json is absent; the sandbox view will report the fixture as missing.');
}

console.log(`sync-data: source ${source}${process.env.LAB_DATA_DIR ? ' (LAB_DATA_DIR override)' : ''}`);
console.log(`sync-data: copied ${copied.length} file(s) into ${relative(appDir, target)}/`);
for (const c of copied) console.log(`  ${c}`);
