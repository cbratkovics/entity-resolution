import { describe, expect, it } from 'vitest';
import { gzipSync } from 'node:zlib';
import { CsvError, gunzipToText, hasDecompressionStream, parseReplayCsv, serialiseReplayCsv } from './csv';
import { evaluate, makePolicy, rowAt, typedRowsFromObjects, type ReplayRow } from './policy';

const HEADER = 'v1,v2,n_candidates,labelled,top1_correct,truth_reachable';

describe('replay csv parsing', () => {
  it('parses nulls, floats and booleans into typed arrays', () => {
    const text = [HEADER, '0.9,0.1,2,true,true,true', '0.99,,1,false,,', ',,0,true,,false', '1e-1,0.05,3,true,false,true', ''].join('\n');
    const rows = parseReplayCsv(text, 4);
    expect(rows.length).toBe(4);
    expect(rowAt(rows, 0)).toEqual({ v1: 0.9, v2: 0.1, n_candidates: 2, labelled: true, top1_correct: true, truth_reachable: true });
    expect(rowAt(rows, 1)).toEqual({ v1: 0.99, v2: null, n_candidates: 1, labelled: false, top1_correct: null, truth_reachable: null });
    expect(rowAt(rows, 2)).toEqual({ v1: null, v2: null, n_candidates: 0, labelled: true, top1_correct: null, truth_reachable: false });
    expect(rowAt(rows, 3)?.v1).toBe(0.1);
  });

  it('rejects a wrong header, a wrong row count and invariant violations', () => {
    expect(() => parseReplayCsv('a,b\n1,2\n', 1)).toThrow(CsvError);
    expect(() => parseReplayCsv(`${HEADER}\n0.9,0.1,2,true,true,true\n`, 2)).toThrow(/row count/);
    expect(() => parseReplayCsv(`${HEADER}\n0.9,0.95,2,true,true,true\n`, 1)).toThrow(/v2 must not exceed/);
    expect(() => parseReplayCsv(`${HEADER}\n0.9,,2,true,true,true\n`, 1)).toThrow(/v2 must be present/);
    expect(() => parseReplayCsv(`${HEADER}\n0.9,0.1,2,false,true,\n`, 1)).toThrow(/unlabelled/);
    expect(() => parseReplayCsv(`${HEADER}\n0.9,0.1,2,true,,true\n`, 1)).toThrow(/top1_correct/);
    expect(() => parseReplayCsv(`${HEADER}\nNaN,,1,false,,\n`, 1)).toThrow(/not a number/);
    expect(() => parseReplayCsv(`${HEADER}\n0.9,0.1,2,yes,true,true\n`, 1)).toThrow(/true, false or empty/);
    expect(() => parseReplayCsv(`${HEADER}\n0.9,0.1,2,true,true\n`, 1)).toThrow(/6 fields/);
  });

  it('round-trips through serialise and parse, and evaluates identically', () => {
    const rows: ReplayRow[] = [
      { v1: 0.95, v2: 0.5, n_candidates: 2, labelled: true, top1_correct: true, truth_reachable: true },
      { v1: 0.7, v2: null, n_candidates: 1, labelled: true, top1_correct: false, truth_reachable: true },
      { v1: null, v2: null, n_candidates: 0, labelled: false, top1_correct: null, truth_reachable: null },
      { v1: 0.0756756772994995, v2: 0.01, n_candidates: 5, labelled: false, top1_correct: null, truth_reachable: null },
    ];
    const typed = typedRowsFromObjects(rows);
    const text = serialiseReplayCsv(typed);
    const back = parseReplayCsv(text, rows.length);
    for (let i = 0; i < rows.length; i += 1) expect(rowAt(back, i)).toEqual(rows[i]);
    const p = makePolicy(0.9, 0.5, 0.1);
    expect(evaluate(back, p)).toEqual(evaluate(rows, p));
  });

  it('decompresses gzip with DecompressionStream when available', async () => {
    if (!hasDecompressionStream()) return;
    const text = `${HEADER}\n0.9,0.1,2,true,true,true\n`;
    const gz = gzipSync(Buffer.from(text));
    const out = await gunzipToText(gz.buffer.slice(gz.byteOffset, gz.byteOffset + gz.byteLength) as ArrayBuffer);
    expect(out).toBe(text);
  });
});
