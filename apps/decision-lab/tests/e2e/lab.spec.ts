/**
 * End-to-end checks against the built app served at the Pages base path. No measured value is
 * hardcoded: every expectation is a structural invariant or a comparison with the data files
 * the app itself serves.
 */
import { expect, test, type Page } from '@playwright/test';
import { readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { gzipSync } from 'node:zlib';

const BASE = '/entity-resolution/lab/';
const ORIGIN = 'http://127.0.0.1:4173';

interface FloorPoint {
  floor: number;
  queue_floor: number;
  queue_ambiguity: number;
  queue_total: number;
  recall_with_review: number | null;
}
interface Snapshot {
  snapshot_id: string;
  methods: Record<string, { policy: { accept_min: number; review_min: number; ambiguity_gap: number }; review_floor: { points: FloorPoint[] } }>;
}
interface Manifest {
  snapshot_id: string;
  analytical_digest: string;
  sources: { sha256: string }[];
  capabilities: { complete_replay: Record<string, { available: boolean; note: string }> };
}
interface Cases {
  cases: { a_id: string; reason_codes: string[]; evidence: ({ exported: true; method_version: string; b_id: string } | { exported: false })[] }[];
  selection: { counts_by_reason: Record<string, number> };
}

async function data<T>(page: Page, rel: string): Promise<T> {
  const r = await page.request.get(`${ORIGIN}${BASE}data/${rel}`);
  expect(r.ok()).toBe(true);
  return (await r.json()) as T;
}

test.describe('decision lab', () => {
  test('compare: three method rows, frozen snapshot id, floor control and budget', async ({ page }) => {
    const requests: string[] = [];
    page.on('request', (r) => requests.push(r.url()));
    await page.goto(`${ORIGIN}${BASE}`);
    const snapshot = await data<Snapshot>(page, 'snapshot.json');
    await expect(page.getByTestId('snapshot-id')).toHaveText(snapshot.snapshot_id);
    await expect(page.getByTestId('identity-line')).toContainText('frozen benchmark, immutable');
    const rows = page.locator('[data-testid^="method-row-"]');
    await expect(rows).toHaveCount(Object.keys(snapshot.methods).length);
    expect(Object.keys(snapshot.methods).length).toBe(3);
    // default screen must not fetch cases or replay bundles
    expect(requests.some((u) => u.includes('cases.json') || u.includes('/replay/'))).toBe(false);
    // every request stays under the base path on the same origin
    for (const u of requests) expect(u.startsWith(`${ORIGIN}${BASE}`), u).toBe(true);
    // root results link resolves to ../
    await expect(page.getByTestId('link-results')).toHaveAttribute('href', '../');
    const resolved = await page.getByTestId('link-results').evaluate((a) => (a as HTMLAnchorElement).href);
    expect(resolved).toBe(`${ORIGIN}/entity-resolution/`);

    // supported floor: pick the first exported floor of the selected method
    const method = await page.getByTestId('floor-method').inputValue();
    const points = [...snapshot.methods[method]!.review_floor.points].sort((a, b) => a.floor - b.floor);
    test.skip(points.length === 0, 'no exported floor points');
    const p = points[0]!;
    await page.getByTestId('floor-select').selectOption(String(p.floor));
    await expect(page.getByTestId('selected-floor-row')).toBeVisible();
    await expect(page.getByTestId('sel-queue-total')).toHaveText(p.queue_total.toLocaleString('en-US'));
    await expect(page.getByTestId('sel-queue-floor')).toHaveText(p.queue_floor.toLocaleString('en-US'));
    await expect(page.getByTestId('fixed-text')).toContainText('only the floor moved');
    await expect(page.getByTestId('fixed-text')).toContainText(`accept_min = ${snapshot.methods[method]!.policy.accept_min}`);
    expect(page.url()).toContain(`floor=${p.floor}`);
    await expect(page.getByTestId('baseline-row')).toBeVisible();

    // budget larger than any queue -> feasible list non-empty
    const allPoints = Object.values(snapshot.methods).flatMap((m) => m.review_floor.points);
    const maxQueue = Math.max(...allPoints.map((x) => x.queue_total));
    const minQueue = Math.min(...allPoints.map((x) => x.queue_total));
    await page.getByTestId('budget-input').fill(String(maxQueue + 1));
    await page.getByTestId('budget-apply').click();
    await expect(page.getByTestId('feasible-table')).toBeVisible();
    expect(await page.getByTestId('feasible-table').locator('tbody tr').count()).toBe(allPoints.length);
    if (minQueue > 0) {
      await page.getByTestId('budget-input').fill('0');
      await page.getByTestId('budget-apply').click();
      await expect(page.getByTestId('budget-result')).toContainText('no supported setting meets this budget');
    }
    // evidence panel always carries the threshold caveat
    await expect(page.getByTestId('evidence-says')).toContainText('not an equal-recall comparison');
  });

  test('cases: filter, open a case, evidence rows, allowlisted links, decisions, consequences, frozen metrics', async ({ page }) => {
    await page.goto(`${ORIGIN}${BASE}#/compare`);
    await expect(page.getByTestId('methods-table')).toBeVisible();
    const before = await page.getByTestId('methods-table').innerHTML();
    const cases = await data<Cases>(page, 'cases.json');
    const first = cases.cases[0]!;

    await page.getByTestId('tab-cases').click();
    await expect(page.getByTestId('case-list')).toBeVisible();
    const total = cases.cases.length;
    await expect(page.getByTestId('filter-count')).toContainText(`${total} of ${total}`);
    const reason = first.reason_codes[0]!;
    await page.getByTestId(`filter-reason-${reason}`).check();
    const expectedCount = cases.cases.filter((c) => c.reason_codes.includes(reason)).length;
    await expect(page.getByTestId('filter-count')).toContainText(`${expectedCount} of ${total}`);
    expect(await page.getByTestId('case-item').count()).toBe(expectedCount);
    await page.getByTestId(`filter-reason-${reason}`).uncheck();
    // an impossible search gives the empty state
    await page.getByTestId('filter-search').fill('zzzz-not-an-id');
    await expect(page.getByTestId('empty-cases')).toBeVisible();
    await page.getByTestId('filter-search').fill('');

    await page.getByTestId('case-link').first().click();
    await expect(page.getByTestId('case-detail')).toBeVisible();
    expect(page.url()).toContain(`#/cases/${first.a_id}`);
    await expect(page.locator('[data-testid^="evidence-row-"]')).toHaveCount(3);
    const mb = page.getByTestId('link-mb').first();
    await expect(mb).toHaveAttribute('href', `https://musicbrainz.org/release-group/${first.a_id}`);
    const exported = first.evidence.filter((e): e is { exported: true; method_version: string; b_id: string } => e.exported);
    if (exported.length) {
      const hrefs = await page.getByTestId('link-discogs').evaluateAll((els) => els.map((e) => (e as HTMLAnchorElement).href));
      expect(hrefs.length).toBeGreaterThan(0);
      for (const h of hrefs) expect(h.startsWith('https://www.discogs.com/master/')).toBe(true);
    }

    // switch method scenario
    await page.getByTestId('scenario-method').selectOption('rules_v1');
    await expect(page.getByTestId('scenario-id')).toHaveText('native:rules_v1');
    await page.getByTestId('scenario-method').selectOption('exact_v1');
    await expect(page.getByTestId('scenario-id')).toHaveText('native:exact_v1');

    // record decisions and watch effective state and consequences
    const cq = page.getByTestId('consequences');
    await expect(cq.getByTestId('cq-accepted')).toHaveText('0');
    const candidate = await page.getByTestId('candidate-select').inputValue();
    test.skip(!candidate, 'case has no candidate to accept');
    await page.getByTestId('btn-accept').click();
    await expect(page.getByTestId('effective-state')).toContainText('accepted');
    await expect(cq.getByTestId('cq-accepted')).toHaveText('1');
    await page.getByTestId('btn-reject').click();
    await expect(page.getByTestId('effective-state')).toContainText('rejected');
    await expect(cq.getByTestId('cq-accepted')).toHaveText('0');
    await expect(cq.getByTestId('cq-rejected')).toHaveText('1');
    await page.getByTestId('btn-defer').click();
    await expect(page.getByTestId('effective-state')).toContainText('deferred');
    await expect(cq.getByTestId('cq-deferred')).toHaveText('1');
    await page.getByTestId('btn-undo').click();
    await expect(cq.getByTestId('cq-deferred')).toHaveText('0');
    await expect(page.getByTestId('effective-state')).toContainText('rejected');

    // the frozen metrics table is byte-identical
    await page.getByTestId('tab-compare').click();
    await expect(page.getByTestId('methods-table')).toBeVisible();
    const after = await page.getByTestId('methods-table').innerHTML();
    expect(after).toBe(before);

    // export the ledger, re-import it (parity), then a tampered snapshot id is rejected
    await page.getByTestId('tab-receipt').click();
    const [download] = await Promise.all([page.waitForEvent('download'), page.getByTestId('ledger-export').click()]);
    const path = join(tmpdir(), `erlab-ledger-${Date.now()}.json`);
    await download.saveAs(path);
    const doc = JSON.parse(readFileSync(path, 'utf8')) as { snapshot: { snapshot_id: string }; events: unknown[] };
    expect(doc.events.length).toBe(4);
    await page.getByTestId('ledger-import').setInputFiles(path);
    await expect(page.getByTestId('ledger-import-ok')).toContainText('imported 0 new event(s); ledger now has 4 events');
    const tampered = join(tmpdir(), `erlab-ledger-tampered-${Date.now()}.json`);
    writeFileSync(tampered, JSON.stringify({ ...doc, snapshot: { ...doc.snapshot, snapshot_id: '20000101T000000+0000@000000000000' } }));
    await page.getByTestId('ledger-import').setInputFiles(tampered);
    await expect(page.getByTestId('ledger-import-rejected')).toContainText('incompatible snapshot');
    const corrupt = join(tmpdir(), `erlab-ledger-corrupt-${Date.now()}.json`);
    writeFileSync(corrupt, '{"review_events_version": "1.0", broken');
    await page.getByTestId('ledger-import').setInputFiles(corrupt);
    await expect(page.getByTestId('ledger-import-rejected')).toContainText('corrupted or invalid file');

    // receipt export produces a file named after the snapshot
    const [receiptDl] = await Promise.all([page.waitForEvent('download'), page.getByTestId('receipt-export').click()]);
    expect(receiptDl.suggestedFilename()).toMatch(/^receipt-.*\.json$/);
    const rpath = join(tmpdir(), receiptDl.suggestedFilename());
    await receiptDl.saveAs(rpath);
    await page.getByTestId('receipt-import').setInputFiles(rpath);
    await expect(page.getByTestId('receipt-import-ok')).toBeVisible();
    const rdoc = JSON.parse(readFileSync(rpath, 'utf8')) as { snapshot: { analytical_digest: string } };
    const rtampered = join(tmpdir(), `erlab-receipt-tampered-${Date.now()}.json`);
    writeFileSync(rtampered, JSON.stringify({ ...rdoc, snapshot: { ...rdoc.snapshot, analytical_digest: 'f'.repeat(64) } }));
    await page.getByTestId('receipt-import').setInputFiles(rtampered);
    await expect(page.getByTestId('receipt-import-rejected')).toContainText('incompatible snapshot');

    // reset with confirmation
    await page.getByTestId('ledger-reset').click();
    await page.getByTestId('confirm-yes').click();
    await expect(page.getByTestId('ledger-export')).toContainText('(0 events)');
    await page.goto(`${ORIGIN}${BASE}#/cases/${first.a_id}`);
    await expect(page.getByTestId('effective-state')).toContainText('no local decision');
  });

  test('provenance and direct loads', async ({ page }) => {
    const manifest = await data<Manifest>(page, 'manifest.json');
    await page.goto(`${ORIGIN}${BASE}#/provenance`);
    await expect(page.getByTestId('analytical-digest')).toHaveText(manifest.analytical_digest);
    const shas = await page.getByTestId('source-sha').allTextContents();
    expect(shas).toEqual(manifest.sources.map((s) => s.sha256));
    await expect(page.getByTestId('build-metadata')).toBeVisible();
    const cases = await data<Cases>(page, 'cases.json');
    await page.goto(`${ORIGIN}${BASE}#/cases/${cases.cases[0]!.a_id}`);
    await expect(page.getByTestId('case-detail')).toBeVisible();
  });

  test('sandbox shows the badge and passes the regression case expectations', async ({ page }) => {
    await page.goto(`${ORIGIN}${BASE}#/sandbox`);
    await expect(page.getByTestId('synthetic-badge')).toBeVisible();
    await expect(page).toHaveTitle(/SYNTHETIC/);
    await expect(page.getByTestId('sandbox-scenario-id')).toContainText('synthetic:');
    const regression = page.locator('[data-testid^="sandbox-checks-"][data-testid*="regression"]').first();
    await expect(regression).toBeVisible();
    const items = await regression.locator('li').allTextContents();
    expect(items.length).toBeGreaterThan(0);
    for (const t of items) expect(t).toContain('pass');
    for (const t of items) expect(t).not.toContain('fail');
    const failing = await page.locator('[data-testid^="sandbox-checks-"] .bad-text').count();
    expect(failing).toBe(0);
    await expect(page.getByTestId('join-demo')).toBeVisible();
  });

  test('replay at the native policy reconciles; unavailable method is disabled', async ({ page }) => {
    const manifest = await data<Manifest>(page, 'manifest.json');
    await page.goto(`${ORIGIN}${BASE}#/replay`);
    const available = Object.entries(manifest.capabilities.complete_replay).filter(([, c]) => c.available).map(([m]) => m);
    for (const [m, c] of Object.entries(manifest.capabilities.complete_replay)) {
      if (!c.available) await expect(page.getByTestId(`replay-unavailable-${m}`)).toContainText(c.note);
    }
    test.skip(!available.includes('rules_v1'), 'rules_v1 replay bundle not available in this export');
    // Serve the bundle as opaque gzip bytes (as GitHub Pages does) so the browser-side
    // DecompressionStream path is exercised; vite preview would otherwise inflate it itself.
    await page.route('**/data/replay/*.csv.gz', async (route) => {
      const res = await route.fetch();
      const body = await res.body();
      const raw = body[0] === 0x1f && body[1] === 0x8b ? body : gzipSync(body);
      await route.fulfill({ status: 200, body: raw, headers: { 'content-type': 'application/gzip' } });
    });
    await page.getByTestId('replay-method').selectOption('rules_v1');
    await expect(page.getByTestId('replay-run')).toBeEnabled({ timeout: 60_000 });
    await page.getByTestId('replay-run').click();
    await expect(page.getByTestId('reconcile-ok')).toContainText('reconciles to the frozen evaluation artifact', { timeout: 60_000 });
    await expect(page.getByTestId('tier-counts')).toBeVisible();
    // invalid policy disables Run
    await page.getByTestId('replay-review').fill('0.99');
    await page.getByTestId('replay-accept').fill('0.5');
    await expect(page.getByTestId('replay-invalid')).toBeVisible();
    await expect(page.getByTestId('replay-run')).toBeDisabled();
  });

  test('error states: fetch failure, malformed data and missing DecompressionStream', async ({ page }) => {
    await page.route('**/data/snapshot.json', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: '{"lab_snapshot_version":"1.0"}' }));
    await page.goto(`${ORIGIN}${BASE}`);
    await expect(page.getByRole('alert')).toContainText('Malformed data');
    await page.unroute('**/data/snapshot.json');
    await page.route('**/data/manifest.json', (route) => route.abort());
    await page.goto(`${ORIGIN}${BASE}`);
    await expect(page.getByRole('alert')).toContainText('Data could not be loaded');
    await page.unroute('**/data/manifest.json');
    await page.goto('about:blank'); // a hash-only navigation would not reload the app
    await page.addInitScript(() => {
      // simulate a browser without DecompressionStream
      Object.defineProperty(window, 'DecompressionStream', { value: undefined, configurable: true });
    });
    await page.route('**/data/replay/*.csv.gz', async (route) => {
      const res = await route.fetch();
      const body = await res.body();
      const raw = body[0] === 0x1f && body[1] === 0x8b ? body : gzipSync(body);
      await route.fulfill({ status: 200, body: raw, headers: { 'content-type': 'application/gzip' } });
    });
    await page.goto(`${ORIGIN}${BASE}#/replay`);
    const manifest = await data<Manifest>(page, 'manifest.json');
    const anyAvailable = Object.values(manifest.capabilities.complete_replay).some((c) => c.available);
    if (anyAvailable) await expect(page.getByTestId('replay-unsupported')).toContainText('complete replay needs a browser with DecompressionStream');
    await page.getByTestId('tab-compare').click();
    await expect(page.getByTestId('methods-table')).toBeVisible();
  });
});
