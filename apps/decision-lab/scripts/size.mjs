#!/usr/bin/env node
/** Print raw and gzip sizes of the built JS/CSS bundles and of every data file the app serves. */
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative, resolve, dirname } from 'node:path';
import { gzipSync } from 'node:zlib';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const appDir = resolve(here, '..');
const dist = join(appDir, 'dist');
const data = join(appDir, 'public', 'data');

function walk(dir) {
  const out = [];
  if (!existsSync(dir)) return out;
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) out.push(...walk(p));
    else out.push(p);
  }
  return out;
}

function kb(n) {
  return (n / 1024).toFixed(1).padStart(8) + ' kB';
}

function report(title, files, base) {
  console.log(`\n${title}`);
  let raw = 0;
  let gz = 0;
  for (const f of files.sort()) {
    const buf = readFileSync(f);
    const g = f.endsWith('.gz') ? buf.length : gzipSync(buf, { level: 9 }).length;
    raw += buf.length;
    gz += g;
    console.log(`${kb(buf.length)} raw ${kb(g)} gzip  ${relative(base, f)}`);
  }
  console.log(`${kb(raw)} raw ${kb(gz)} gzip  total`);
}

const bundles = walk(join(dist, 'assets')).filter((f) => /\.(js|css)$/.test(f));
if (bundles.length === 0) {
  console.log('size: no built bundle in dist/assets (run `npm run build` first)');
} else {
  report('Bundles (dist/assets)', bundles, dist);
}
const dataFiles = walk(data);
if (dataFiles.length === 0) {
  console.log('size: no data files in public/data (run `npm run sync-data`)');
} else {
  report('Data files (public/data; .gz files are already compressed)', dataFiles, data);
  const defaultScreen = dataFiles.filter((f) => /(^|\/)(manifest|snapshot)\.json$/.test(f));
  report('Default screen payload (manifest + snapshot only)', defaultScreen, data);
}
