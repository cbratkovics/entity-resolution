import { useEffect, useRef, type ReactNode } from 'react';
import type { LoadError } from '../lib/data';

export function Loading({ what }: { what: string }) {
  return (
    <p className="muted" role="status">
      Loading {what}…
    </p>
  );
}

export function ErrorState({ error, title }: { error: LoadError; title?: string }) {
  const heading =
    error.kind === 'malformed' ? 'Malformed data' : error.kind === 'unsupported' ? 'Unsupported in this browser' : 'Data could not be loaded';
  return (
    <div className="error" role="alert">
      <strong>{title ?? heading}</strong>
      <p className="small wrap">
        {error.message} <span className="muted">(file: {error.file})</span>
      </p>
      {error.kind === 'fetch_failed' ? (
        <p className="small muted">The app only reads its own data files under its base path. Check that the export was synced into public/data/.</p>
      ) : null}
    </div>
  );
}

export function MethodName({ method }: { method: string }) {
  return <span className={`mono method-${method}`}>{method}</span>;
}

/** An inline "why" popover rendered with a native disclosure (keyboard operable, no JS). */
export function Why({ label = 'why?', children }: { label?: string; children: ReactNode }) {
  return (
    <details className="why">
      <summary>{label}</summary>
      <div>{children}</div>
    </details>
  );
}

export function FrozenBadge() {
  return <span className="badge frozen">frozen benchmark, immutable</span>;
}

export function ConfirmDialog({
  open,
  title,
  body,
  confirmLabel,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  body: string;
  confirmLabel: string;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) {
      if (typeof d.showModal === 'function') d.showModal();
      else d.setAttribute('open', '');
    } else if (!open && d.open) {
      d.close();
    }
  }, [open]);
  return (
    <dialog ref={ref} aria-labelledby="confirm-title" onCancel={onCancel} onClose={onCancel}>
      <h2 id="confirm-title" style={{ marginTop: 0 }}>
        {title}
      </h2>
      <p>{body}</p>
      <div className="button-row">
        <button type="button" onClick={onCancel}>
          Cancel
        </button>
        <button type="button" className="danger" onClick={onConfirm} data-testid="confirm-yes">
          {confirmLabel}
        </button>
      </div>
    </dialog>
  );
}

export function StatusLive({ message }: { message: string }) {
  return (
    <div role="status" aria-live="polite" className="sr-only" data-testid="status-live">
      {message}
    </div>
  );
}

export function KeyValue({ rows }: { rows: [string, ReactNode][] }) {
  return (
    <dl className="kv">
      {rows.map(([k, v]) => (
        <div key={k} style={{ display: 'contents' }}>
          <dt>{k}</dt>
          <dd>{v}</dd>
        </div>
      ))}
    </dl>
  );
}
