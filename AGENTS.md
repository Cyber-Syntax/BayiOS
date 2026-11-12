# BayiOS

LAN-only dealer operations system for a Turkish appliance dealer: products, imports, stock, reservations, campaigns, offers, commissions, and A4 printouts.

## Project

- Modular monolith: FastAPI + Jinja2 + HTMX + Alpine.js, PostgreSQL 17, SQLAlchemy 2, Alembic, Pydantic. Python 3.13, managed with `uv`.
- Entry point: `src/bayios/main.py:create_app` (`bayios` console script calls `bayios:main`). Wiring and settings live in `src/bayios/bootstrap.py`.
- MVP has **no authentication, roles, or permissions**; it is designed for a trusted local network only.
- Product docs: `docs/prd.md` (what/why), `docs/plan.md` (architecture and milestone contracts), `docs/ui.md` (UI contract), `GLOSSARY.md` (domain vocabulary), `docs/adr/` (accepted decisions).
- Source of truth when docs disagree: **code > `docs/plan.md` > `docs/prd.md`**. Parts of the PRD are stale (e.g. it mentions Tailwind and a separate `backend/frontend` tree; neither exists).

## Commands

```bash
uv sync                                     # install dependencies (uv.lock)
bash scripts/dev.sh                         # dev Postgres + migrations + uvicorn --reload
uv run uvicorn bayios.main:create_app --factory --reload
uv run alembic upgrade head                 # apply migrations (head: 0011)
uv run alembic revision -m "message"        # add a migration
uv run pytest -q                            # full suite: 215 tests, 4 skipped without a test DB
BAYIOS_TEST_DATABASE_URL=postgresql+psycopg://bayios:bayios@127.0.0.1:5432/bayios_test \
  uv run pytest tests/integration -q        # PostgreSQL integration tests
uv run ruff check src tests                 # lint (currently clean)
```

- `DATABASE_URL` is required and must use `postgresql+psycopg://`; there is no SQLite fallback. Copy `.env.example` to `.env` for local runs.
- Do **not** run `ruff format`: it would reformat ~57 files; the repo is not formatted with it.
- Production: Podman Compose (`compose.yaml`), see `docs/OPERATIONS.md` and `docs/RELEASE.md`. Postgres is never published to the host.
- Verification: run the targeted tests for the area you change plus `ruff check`; run the full `uv run pytest` before declaring work done.

## Architecture

- `src/bayios/domain/` — pure rules and value objects only: product/category normalization, stock summary and count policy, reservation state transitions, campaign scenarios, commission math, offer pricing. No FastAPI, SQLAlchemy, filesystem, or clock access.
- `src/bayios/application/` — use cases (commands/queries) and transaction orchestration; typed errors in `application/errors.py`; ports in `application/ports/`. Each feature is a package (`products`, `imports`, `inventory`, `reservations`, `campaigns`, `dealer_pricing`, `offers`, `commissions`).
- `src/bayios/adapters/db/` — SQLAlchemy models (`models/`), repositories (`repositories/`), and `unit_of_work.py`. `models/base.py` provides `Base`, `MONEY` (`Numeric(12, 2)`), and `uuid_pk()`. `health.py` checks DB and Alembic head.
- `src/bayios/web/` — FastAPI routers in `pages/` and `api/`, Jinja templates, static assets, `deps.py` (`UnitOfWorkDep`, `ActorDep`), `navigation.py`, `templating.py` (Turkish filters).
- `tests/fakes.py` — `FakeUnitOfWork` used by application and web tests; web tests override `get_unit_of_work`. `tests/integration/` uses real PostgreSQL and is skipped unless `BAYIOS_TEST_DATABASE_URL` is set.

Route handlers stay thin: parse the request, call an application use case with a unit of work, render a template/redirect. Business rules belong in `application/` or `domain/`, never in routers or templates.

## Conventions

- **Language:** all user-facing text is Turkish — UI labels, validation/conflict messages, flash messages, print output. Comments, docstrings, identifiers, logs, and technical errors are English. English technical messages must never leak into the UI; domain/application code may raise Turkish user-facing messages.
- **Money:** always `Decimal`/`NUMERIC`, two decimals, `ROUND_HALF_UP`. Never use `float`. Render with the Jinja filters `tr_money` and `tr_percent`.
- **Dates:** store UTC, display `Europe/Istanbul` via `tr_date` (`10.11.2026`), `tr_date_long` (`10 Kasım 2026`), `tr_datetime`, and `iso_date` for form values. Date inputs use Flatpickr with the Turkish locale; ISO stays the submitted value.
- **Product identity:** match only on `name_normalized` (Unicode NFKC, whitespace collapse, Turkish `I/ı/İ/i` folding, leading zeros preserved). No fuzzy matching; ambiguity surfaces as a conflict for the user.
- **Stock semantics:** physical stock is directly sellable. Reservations never reserve or reduce stock; only marking a reservation line `DELIVERED` reduces stock via an idempotent `delivery_out` movement. `stock_movements` is append-only.
- **Transactions:** use `with uow:` and call `uow.commit()` explicitly. A failed operation must roll back and must never render as success.
- **UI:** server-rendered Jinja2; HTMX only for partial updates (`_*.html` fragments); Alpine.js only for local UI state. No CDN and no runtime internet dependency. Vendored assets live in `web/static/vendor/` with hashes in `VERSIONS.txt`.
- **CSS:** edit `web/static/css/app.css` and `print.css` directly. No Tailwind, Node, or CSS build step.
- **Immutability:** campaign versions, offer snapshots, commission periods, and reservation events are append-only; edits must not rewrite history. Only actual changes create history/version rows.
- **Migrations:** Alembic revisions follow `00NN_slug.py`, forward-only; never edit an applied revision.
- **Out of scope:** auth/roles, web scraping, WMS/Dynamics integration, POS basket optimization, PDF attachments, barcode product lookup, and manual barcode entry. Do not imply these exist.
- **Tests:** assert observable behavior, not implementation details. Use `FakeUnitOfWork` for application/web tests; add PostgreSQL integration coverage for transaction, idempotency, and concurrency changes. Keep Turkish UI strings exact in assertions.

## Agent skills

### Issue tracker

Issues and specs live in GitHub Issues and are managed with `gh`. See `docs/agents/issue-tracker.md`.

### Domain docs

This is a single-context repository with root `GLOSSARY.md` and `docs/adr/`. See `docs/agents/domain.md`.
