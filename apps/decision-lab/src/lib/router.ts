/** Hash routing that survives direct loads on GitHub Pages: `#/view?query`. */
export const VIEWS = ['compare', 'cases', 'replay', 'sandbox', 'receipt', 'provenance'] as const;
export type View = (typeof VIEWS)[number];

export interface Route {
  view: View;
  /** `#/cases/<a_id>` */
  caseId: string | null;
  params: URLSearchParams;
}

export function parseHash(hash: string): Route {
  let h = hash.startsWith('#') ? hash.slice(1) : hash;
  if (!h.startsWith('/')) h = '/' + h;
  const q = h.indexOf('?');
  const path = q === -1 ? h : h.slice(0, q);
  const params = new URLSearchParams(q === -1 ? '' : h.slice(q + 1));
  const parts = path.split('/').filter((p) => p.length > 0);
  const first = parts[0] ?? 'compare';
  const view: View = (VIEWS as readonly string[]).includes(first) ? (first as View) : 'compare';
  const caseId = view === 'cases' && parts[1] ? decodeURIComponent(parts[1]).slice(0, 80) : null;
  return { view, caseId, params };
}

export function buildHash(view: View, opts: { caseId?: string | null; query?: string } = {}): string {
  const c = opts.caseId ? `/${encodeURIComponent(opts.caseId)}` : '';
  const q = opts.query ?? '';
  return `#/${view}${c}${q}`;
}
