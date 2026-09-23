.PHONY: help setup lint format test dbt full smoke docs

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
	@echo "dbt    - dbt deps + build the warehouse from the committed artifacts + docs generate + description check"
	@echo "full   - the full build over the real dumps (network, hours): entity_resolution.pipeline.match"
	@echo "smoke  - clone HEAD (+ uncommitted changes) into a temp dir and run setup lint test dbt docs there"
	@echo "docs   - regenerate docs/METHODS_CARD.md, check docs/PROFILE.md is current, run the number and placeholder checks"

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
	$(PY) scripts/check_numbers.py
