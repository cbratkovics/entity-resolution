/**
 * Replay bundle CSV: header `v1,v2,n_candidates,labelled,top1_correct,truth_reachable`, one row
 * per test-fold A record, empty field = null, floats in shortest round-trip form, booleans
 * `true`/`false`. Parsed line by line into typed arrays (see `TypedRows` in policy.ts).
 */
import { REPLAY_COLUMNS } from './contracts';
import {
  FLAG_LABELLED,
  FLAG_REACHABLE,
  FLAG_REACHABLE_PRESENT,
  FLAG_TOP1_CORRECT,
  FLAG_TOP1_PRESENT,
  type TypedRows,
} from './policy';

export class CsvError extends Error {
  override name = 'CsvError';
}

export function hasDecompressionStream(): boolean {
  return typeof DecompressionStream === 'function' && typeof Response === 'function';
}

/** True when the bytes start with the gzip magic number (1f 8b). */
export function isGzip(buffer: ArrayBuffer): boolean {
  const b = new Uint8Array(buffer);
  return b.length >= 2 && b[0] === 0x1f && b[1] === 0x8b;
}

/**
 * Bytes of a replay bundle to CSV text. Static hosts differ: GitHub Pages serves `.csv.gz` as
 * opaque gzip bytes (decompressed here with DecompressionStream), while some dev servers send
 * `Content-Encoding: gzip` so the browser has already inflated them; the magic number decides.
 */
export async function bundleBytesToText(buffer: ArrayBuffer): Promise<string> {
  if (!isGzip(buffer)) return new TextDecoder('utf-8').decode(buffer);
  return gunzipToText(buffer);
}

/** Inflate a gzip payload with the browser's DecompressionStream; callers feature-detect first. */
export async function gunzipToText(buffer: ArrayBuffer): Promise<string> {
  if (!hasDecompressionStream()) {
    throw new CsvError('DecompressionStream is not available in this browser');
  }
  const stream = new Blob([buffer]).stream().pipeThrough(new DecompressionStream('gzip'));
  return new Response(stream).text();
}

function parseValue(field: string, line: number, col: string): number {
  if (field === '') return NaN;
  // Accept plain decimal / exponent forms only; reject anything else (no NaN/Infinity tokens).
  if (!/^-?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?$/.test(field)) {
    throw new CsvError(`line ${line}: ${col} is not a number: ${field}`);
  }
  const v = Number(field);
  if (!Number.isFinite(v)) throw new CsvError(`line ${line}: ${col} is not finite`);
  return v;
}

function parseBool(field: string, line: number, col: string): boolean | null {
  if (field === '') return null;
  if (field === 'true') return true;
  if (field === 'false') return false;
  throw new CsvError(`line ${line}: ${col} must be true, false or empty, got ${field}`);
}

/**
 * Parse the CSV text into typed arrays. `expectedRows` (from the replay meta) sizes the arrays
 * and is verified against the actual row count. Every row is validated with the ReplayRow
 * invariants, so a bundle that breaks them is rejected as malformed.
 */
export function parseReplayCsv(text: string, expectedRows: number): TypedRows {
  let pos = 0;
  const len = text.length;
  const nextLine = (): string | null => {
    if (pos >= len) return null;
    let end = text.indexOf('\n', pos);
    if (end === -1) end = len;
    let line = text.slice(pos, end);
    pos = end + 1;
    if (line.endsWith('\r')) line = line.slice(0, -1);
    return line;
  };
  const header = nextLine();
  if (header === null) throw new CsvError('empty file');
  const cols = header.split(',');
  if (cols.length !== REPLAY_COLUMNS.length || cols.some((c, i) => c !== REPLAY_COLUMNS[i])) {
    throw new CsvError(`unexpected header: ${header}`);
  }
  const cap = Math.max(expectedRows, 0);
  let v1 = new Float64Array(cap);
  let v2 = new Float64Array(cap);
  let nc = new Uint32Array(cap);
  let flags = new Uint8Array(cap);
  let n = 0;
  let lineNo = 1;
  for (let line = nextLine(); line !== null; line = nextLine()) {
    lineNo += 1;
    if (line === '' && pos >= len) break; // trailing newline
    const f = line.split(',');
    if (f.length !== 6) throw new CsvError(`line ${lineNo}: expected 6 fields, got ${f.length}`);
    const a = parseValue(f[0] as string, lineNo, 'v1');
    const b = parseValue(f[1] as string, lineNo, 'v2');
    const kText = f[2] as string;
    if (!/^\d+$/.test(kText)) throw new CsvError(`line ${lineNo}: n_candidates must be a non-negative integer`);
    const k = Number(kText);
    const labelled = parseBool(f[3] as string, lineNo, 'labelled');
    const top1 = parseBool(f[4] as string, lineNo, 'top1_correct');
    const reach = parseBool(f[5] as string, lineNo, 'truth_reachable');
    if (labelled === null) throw new CsvError(`line ${lineNo}: labelled must be true or false`);
    // ReplayRow invariants (policy.py ReplayRow.__post_init__)
    if (Number.isNaN(a) !== (k === 0)) throw new CsvError(`line ${lineNo}: v1 is null exactly when there is no candidate`);
    if (!Number.isNaN(b) && k < 2) throw new CsvError(`line ${lineNo}: v2 requires at least two candidates`);
    if (Number.isNaN(b) && k >= 2) throw new CsvError(`line ${lineNo}: v2 must be present when there are two or more candidates`);
    if (!Number.isNaN(a) && !Number.isNaN(b) && b > a) throw new CsvError(`line ${lineNo}: v2 must not exceed v1`);
    if (!labelled && (top1 !== null || reach !== null)) throw new CsvError(`line ${lineNo}: unlabelled rows carry no correctness or reachability`);
    if (labelled && reach === null) throw new CsvError(`line ${lineNo}: labelled rows must state truth reachability`);
    if (labelled && !Number.isNaN(a) && top1 === null) throw new CsvError(`line ${lineNo}: labelled rows with a candidate must state top1_correct`);
    if (Number.isNaN(a) && top1 !== null) throw new CsvError(`line ${lineNo}: no candidate means no top1_correct`);
    if (n >= v1.length) {
      const grow = Math.max(1024, v1.length * 2);
      const nv1 = new Float64Array(grow);
      nv1.set(v1);
      v1 = nv1;
      const nv2 = new Float64Array(grow);
      nv2.set(v2);
      v2 = nv2;
      const nnc = new Uint32Array(grow);
      nnc.set(nc);
      nc = nnc;
      const nf = new Uint8Array(grow);
      nf.set(flags);
      flags = nf;
    }
    v1[n] = a;
    v2[n] = b;
    nc[n] = k;
    let fl = 0;
    if (labelled) fl |= FLAG_LABELLED;
    if (top1 !== null) fl |= FLAG_TOP1_PRESENT | (top1 ? FLAG_TOP1_CORRECT : 0);
    if (reach !== null) fl |= FLAG_REACHABLE_PRESENT | (reach ? FLAG_REACHABLE : 0);
    flags[n] = fl;
    n += 1;
  }
  if (n !== expectedRows) throw new CsvError(`row count ${n} does not match the declared ${expectedRows}`);
  return {
    length: n,
    v1: v1.subarray(0, n),
    v2: v2.subarray(0, n),
    n_candidates: nc.subarray(0, n),
    flags: flags.subarray(0, n),
  };
}

/** Serialise typed rows back to the CSV contract (used by the mock generator and tests). */
export function serialiseReplayCsv(rows: TypedRows): string {
  const out: string[] = [REPLAY_COLUMNS.join(',')];
  for (let i = 0; i < rows.length; i += 1) {
    const a = rows.v1[i] as number;
    const b = rows.v2[i] as number;
    const f = rows.flags[i] as number;
    const labelled = (f & FLAG_LABELLED) !== 0;
    const top1 = f & FLAG_TOP1_PRESENT ? String((f & FLAG_TOP1_CORRECT) !== 0) : '';
    const reach = f & FLAG_REACHABLE_PRESENT ? String((f & FLAG_REACHABLE) !== 0) : '';
    out.push(
      [Number.isNaN(a) ? '' : String(a), Number.isNaN(b) ? '' : String(b), String(rows.n_candidates[i]), String(labelled), top1, reach].join(','),
    );
  }
  return out.join('\n') + '\n';
}
