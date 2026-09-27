.PHONY: help setup lint format test dbt full smoke docs lab-export lab-check lab-fixtures lab-dev lab-test lab-build lab-verify lab-export lab-check lab-fixtures

PY ?= .venv/bin/python
PKG = entity_resolution
DBT ?= .venv/bin/dbt
DBT_FLAGS = --project-dir dbt --profiles-dir dbt
# Reproducible warehouse builds: DuckDB's parallel aggregation order is not deterministic, so
# exports can differ at the 1e-15 level between builds; set ENTITY_RESOLUTION_DUCKDB_THREADS=1
# when comparing exports (docs/REPRODUCIBILITY.md).

help:
	@echo "setup  - create .venv from uv.lock (runtime + dev, frozen) and install the dbt packages"
	@echo "lint   - ruff check + ruff format --check + sqlfluff over the dbt project"
	@echo "test   - pytest (offline; real-data tests skip when data/ is absent)"
	@echo "dbt    - build the warehouse from the committed artifacts, docs generate, description check, export gold to docs/site/data"
	@echo "full   - the full build over the real dumps (network, hours): entity_resolution.pipeline.match"
	@echo "smoke  - clone HEAD (+ uncommitted changes) into a temp dir and run setup lint test dbt docs there"
	@echo "docs   - regenerate docs/METHODS_CARD.md, check PROFILE.md, FINDINGS.md and README blocks are current, run the number and placeholder checks"
	@echo "lab-dev    - sync artifacts/lab into the app and run the Vite dev server (Node)"
	@echo "lab-test   - the lab's pytest modules, then npm typecheck, lint and vitest (Node)"
	@echo "lab-build  - production build of apps/decision-lab at /entity-resolution/lab/ and gzip sizes (Node)"
	@echo "lab-verify - lab-check, lab-test, lab-build, then the Playwright journeys against the built app (Node, Chromium)"
	@echo "lab-export   - build artifacts/lab (snapshot, cases, replay bundles when data/ is present) and the decision-lab fixtures"
	@echo "lab-check    - verify artifacts/lab in place: hashes, schemas, allowlist, recomputation, replay reconciliation (no data/ needed)"
	@echo "lab-fixtures - rewrite the shared policy fixtures and the synthetic sandbox under apps/decision-lab/fixtures"

setup:
	uv sync --frozen --all-extras
	$(DBT) deps $(DBT_FLAGS)
	@find dbt/dbt_packages -maxdepth 1 -type d -empty -delete
	mkdir -p .duckdb

# sqlfluff's dbt templater compiles the project against the dev target, so the dbt packages
# must be installed (make setup) and the .duckdb/ directory must exist.
lint:
	$(PY) -m ruff check $(PKG) tests scripts
	$(PY) -m ruff format --check $(PKG) tests scripts
	mkdir -p .duckdb
	.venv/bin/sqlfluff lint dbt/models dbt/tests dbt/macros

format:
	$(PY) -m ruff format $(PKG) tests scripts
	$(PY) -m ruff check --fix $(PKG) tests scripts

test:
	$(PY) -m pytest tests

dbt:
	$(DBT) deps $(DBT_FLAGS)
	@find dbt/dbt_packages -maxdepth 1 -type d -empty -delete
	mkdir -p .duckdb
	$(DBT) build $(DBT_FLAGS) --target dev --full-refresh
	$(DBT) docs generate $(DBT_FLAGS) --target dev --static
	$(PY) scripts/check_dbt_descriptions.py
	mkdir -p docs/site/data
	$(DBT) run-operation export_gold $(DBT_FLAGS) --target dev

# The full build (docs/BRIEF.md 2.12): acquire the dumps, sample, block, feature, fit, decide,
# evaluate, write artifacts/. Refuses to run until the phases that build it are complete.
full:
	$(PY) -m $(PKG).pipeline.match

smoke:
	bash scripts/smoke.sh

docs:
	$(PY) scripts/check_model_card.py --write
	$(PY) scripts/check_model_card.py
	$(PY) scripts/profile_sources.py render --check
	$(PY) scripts/render_findings.py --check
	$(PY) scripts/check_numbers.py

# The decision lab (docs/DECISION_LAB.md): a static export under artifacts/lab built from the
# committed artifacts; the replay bundles and case labels need the hash-verified data/ inputs.
lab-export:
	$(PY) -m $(PKG).decision_lab.cli export

lab-check:
	$(PY) -m $(PKG).decision_lab.cli check

lab-fixtures:
	$(PY) -m $(PKG).decision_lab.cli fixtures
	$(PY) -m $(PKG).decision_lab.cli synthetic

# Node targets (ADR 0006). Every Python-only target above works without Node; these need
# `npm ci` once in apps/decision-lab (lockfile frozen, Node version in apps/decision-lab/.nvmrc).
LAB = apps/decision-lab
NPM = npm --prefix $(LAB)

lab-dev:
	$(NPM) run dev

lab-test:
	$(PY) -m pytest tests/test_lab_policy.py tests/test_lab_export.py tests/test_lab_ledger.py tests/test_lab_synthetic.py tests/test_lab_qa_catalog.py
	$(NPM) run typecheck
	$(NPM) run lint
	$(NPM) test

lab-build:
	$(NPM) run build
	$(NPM) run size

lab-verify: lab-check lab-test lab-build
	$(NPM) run test:e2e
