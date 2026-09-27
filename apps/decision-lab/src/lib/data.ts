/**
 * Data loading: fetch the app's own files under `<base>/data/`, parse and validate strictly.
 * Only the manifest and snapshot are fetched for the default screen; cases, replay bundles and
 * the sandbox fixture are loaded lazily by the views that need them.
 */
import { casesV, manifestV, replayMetaV, sandboxV, snapshotV, type LabCases, type LabManifest, type ReplayMeta, type SyntheticSandbox, type LabSnapshot } from './contracts';
import { bundleBytesToText, CsvError, hasDecompressionStream, isGzip, parseReplayCsv } from './csv';
import { ValidationError, type Validator } from './validate';
import type { TypedRows } from './policy';

export type LoadErrorKind = 'fetch_failed' | 'malformed' | 'unsupported';

export class LoadError extends Error {
  override name = 'LoadError';
  readonly kind: LoadErrorKind;
  readonly file: string;
  constructor(kind: LoadErrorKind, file: string, message: string) {
    super(message);
    this.kind = kind;
    this.file = file;
  }
}

export function dataUrl(relative: string, base: string = import.meta.env.BASE_URL): string {
  const b = base.endsWith('/') ? base : base + '/';
  return `${b}data/${relative}`;
}

async function fetchText(relative: string): Promise<string> {
  let res: Response;
  try {
    res = await fetch(dataUrl(relative), { cache: 'no-cache' });
  } catch (e) {
    throw new LoadError('fetch_failed', relative, `could not fetch ${relative}: ${e instanceof Error ? e.message : String(e)}`);
  }
  if (!res.ok) throw new LoadError('fetch_failed', relative, `could not fetch ${relative}: HTTP ${res.status}`);
  return res.text();
}

async function fetchBuffer(relative: string): Promise<ArrayBuffer> {
  let res: Response;
  try {
    res = await fetch(dataUrl(relative), { cache: 'no-cache' });
  } catch (e) {
    throw new LoadError('fetch_failed', relative, `could not fetch ${relative}: ${e instanceof Error ? e.message : String(e)}`);
  }
  if (!res.ok) throw new LoadError('fetch_failed', relative, `could not fetch ${relative}: HTTP ${res.status}`);
  return res.arrayBuffer();
}

export async function loadJson<T>(relative: string, validator: Validator<T>): Promise<T> {
  const text = await fetchText(relative);
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    throw new LoadError('malformed', relative, `malformed data: ${relative} is not valid JSON`);
  }
  try {
    return validator(parsed, relative);
  } catch (e) {
    if (e instanceof ValidationError) throw new LoadError('malformed', relative, `malformed data: ${e.message}`);
    throw e;
  }
}

export const loadManifest = (): Promise<LabManifest> => loadJson('manifest.json', manifestV);
export const loadSnapshot = (): Promise<LabSnapshot> => loadJson('snapshot.json', snapshotV);
export const loadCases = (): Promise<LabCases> => loadJson('cases.json', casesV);
export const loadSandbox = (): Promise<SyntheticSandbox> => loadJson('synthetic_sandbox.json', sandboxV);

export interface ReplayBundle {
  meta: ReplayMeta;
  rows: TypedRows;
}

/** Load `replay/replay_<method>.json` and its csv.gz; requires DecompressionStream. */
export async function loadReplayBundle(method: string, metaFile?: string, dataFile?: string): Promise<ReplayBundle> {
  const metaRel = metaFile ?? `replay/replay_${method}.json`;
  const meta = await loadJson(metaRel, replayMetaV);
  if (meta.method_version !== method) {
    throw new LoadError('malformed', metaRel, `malformed data: replay meta is for ${meta.method_version}, expected ${method}`);
  }
  const csvRel = dataFile ?? `replay/${meta.file.split('/').pop() ?? meta.file}`;
  const buffer = await fetchBuffer(csvRel);
  if (isGzip(buffer) && !hasDecompressionStream()) {
    throw new LoadError('unsupported', csvRel, 'complete replay needs a browser with DecompressionStream');
  }
  let text: string;
  try {
    text = await bundleBytesToText(buffer);
  } catch (e) {
    throw new LoadError('malformed', csvRel, `malformed data: could not decompress ${csvRel}: ${e instanceof Error ? e.message : String(e)}`);
  }
  try {
    const rows = parseReplayCsv(text, meta.rows);
    return { meta, rows };
  } catch (e) {
    if (e instanceof CsvError) throw new LoadError('malformed', csvRel, `malformed data: ${e.message}`);
    throw e;
  }
}
