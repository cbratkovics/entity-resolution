"""Entity Resolution Decision Lab: contracts, export construction, validation, policy replay,
case selection and decision-record validation for the static lab under ``apps/decision-lab``
(docs/DECISION_LAB.md, ADR 0006 and ADR 0007).

Nothing here refits, calibrates or re-evaluates a method. The package reads the committed
artifacts (and, owner-run, the frozen local outputs under ``data/``), writes deterministic
compact JSON under ``artifacts/lab/`` and checks it. Business logic for the browser lives in
``policy.py`` and is mirrored, fixture for fixture, by ``apps/decision-lab/src/lib/policy.ts``.
"""

LAB_CONTRACT_VERSION = "1.0"
"""Version of every lab contract (manifest, snapshot, cases, replay, receipts, events)."""
