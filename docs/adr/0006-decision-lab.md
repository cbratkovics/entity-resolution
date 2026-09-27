# ADR-0006 — A static Decision Lab beside the results page (2026-09-26)

**Context.** `docs/BRIEF.md` rule `12` scoped v1 to the pipeline, artifacts, warehouse, docs site
and README, with no frontend. The finished v1 answers "how good is each method" but not the
question a matching policy owner actually decides: which records to accept automatically, which
to send to review, which to leave unresolved, and what evidence and trade-offs justify that. The
evidence to answer it already exists in the committed artifacts (the three evaluation
artifacts, the review-floor sweep, the test-fold mapping exhibits), but it is spread over JSON
files and a results page that shows aggregates only.

**Decision.** Add a local-first, static Decision Lab at `/entity-resolution/lab/`, built from
`apps/decision-lab/` (React, TypeScript, Vite; Vitest and Playwright; lockfile committed; Node
pinned in `.nvmrc`) and published inside the existing single Pages artifact under `site/lab/`.
The existing results page and `/dbt/` stay as they are, with navigation between them. A Python
package `entity_resolution/decision_lab/` owns the contracts (`artifacts/schemas/lab_*.schema.json`),
the export builder (`artifacts/lab/`), validation (`--check`), the pure policy specification,
curated-case selection and decision-record validation; the app carries a typed mirror of the
policy specification tested against the same fixtures. The lab reads compact exports, never the
full mapping; `fct_mapping` keeps `meta.export=false`. No backend, accounts, database service,
LLM call, authentication, payment, cloud deployment, dataset upload or global clustering.
Alternatives: extend `docs/site/index.html` (rejected: the case explorer, ledger and replay need
state, routing and tests the plain page was designed not to have); a notebook (rejected: not a
decision product anyone can open); a hosted service (rejected by rule `3`).

**Consequences.** Rule `12` is amended in the amendments log. `ci.yml` gains a lab job (type
check, unit tests, build, browser tests); `pages.yml` builds the app and copies `dist/` to
`site/lab/`; `verify.yml` runs `make lab-check`. Public data restrictions are unchanged: the lab
exports carry identifiers, numbers, controlled reason codes and provenance only, and
`tests/test_no_raw_rows.py` covers them. Readable records exist only in the synthetic sandbox
fixture (`apps/decision-lab/fixtures/synthetic_sandbox.json`, ids `SYN-A-nnn`/`SYN-B-nnn`, a
fixed nonsense vocabulary), which is badged as synthetic in every view and export. Local browser
decisions (review events, receipts) stay on the device unless exported; they are user decisions,
never labels, mapping writes or measured outcomes. The benchmark artifacts are unchanged and the
lab renders them as an immutable baseline.
