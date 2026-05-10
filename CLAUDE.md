# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

`safeway-coupons` is a CLI that auto-clips "Safeway for U" digital coupons for one or more Safeway accounts. Sign-in goes through a headless Chrome session (`undetected-chromedriver`) to get past Safeway's WAF; once a session is established, all coupon listing and clipping happens over plain `requests` HTTP calls reusing the cookies/headers from that session. An optional email summary is sent per account via `sendmail`.

## Common commands

Dependency and tooling are managed by Poetry; task aliases are defined under `[tool.poe.tasks]` in `pyproject.toml`.

- Install dev environment: `poetry install`
- Run the CLI: `poetry run safeway-coupons [options]` (entry point `safeway_coupons.app:main`)
- Run all checks (lint + tests): `poetry run poe test`
- Lint / pre-commit only: `poetry run poe lint` (equivalent to `poetry run pre-commit run --all-files --show-diff-on-failure`)
- Tests only: `poetry run poe pytest` or `poetry run pytest`
- Single test file / node: `poetry run pytest tests/test_safeway.py` or `poetry run pytest tests/test_safeway.py::test_name`
- Type-check: `poetry run mypy` (config in `[tool.mypy]`; `disallow_untyped_defs = true`, so all new functions need annotations)
- One-shot Docker dev run: `docker-compose -f docker-compose.dev.yaml up --build` (requires an `accounts` file alongside the compose file; clips one coupon then exits)

`pytest` always runs with `--cov` appended (see `[tool.pytest.ini_options]`); coverage is written to `.pytest_coverage.xml` and JUnit results to `.pytest_results.xml`.

## Architecture

Entry point is `safeway_coupons/app.py::main`, which parses CLI args, calls `Config.load_accounts(...)` to assemble a list of `Account` objects, then loops over them invoking `SafewayCoupons.clip_for_account(account)`. With `--continue-on-error/-E`, per-account `Error` exceptions are caught and counted instead of aborting.

The clipping pipeline for one account (`safeway_coupons/safeway.py`):

1. Construct `SafewayClient(account, interactive_sign_in, debug_dir)` — this triggers a headless-Chrome login via `chrome_driver.py` / `session.py` (`LoginSession`). `--interactive-sign-in/-I` keeps the browser visible so the user can solve 2FA.
2. `swy.get_offers()` returns `Offer` models (see `models.py`, `dataclasses-json` based) by hitting Safeway's offers endpoint with the auth cookies/headers harvested from the Selenium session.
3. Filter to `OfferStatus.Unclipped`, walk them through `utils.yield_delay(...)` (which paces requests according to `--no-sleep/-S` level), and call `swy.clip(offer)` for each unless `--pretend/--dry-run`. Hard ceilings: `--max-clip` for total clips, and `CLIP_ERROR_MAX = 5` consecutive `ClipError`s raises `TooManyClipErrors`.
4. `email.email_clip_results(...)` / `email.email_error(...)` shells out to `sendmail` (path/args configurable via `--sendmail`) when `send_email` is on and not a dry run.

Module map (`safeway_coupons/`):

- `app.py` — argparse CLI + main loop
- `safeway.py` — `SafewayCoupons` orchestrator (per-account flow, error/email handling)
- `client.py` — `SafewayClient` HTTP API (offers list, clip POSTs, auth-header plumbing)
- `session.py` — `BaseSession` / `LoginSession` (requests session + Selenium-driven login)
- `chrome_driver.py` — headless Chrome bootstrap; also exposed as the `safeway-coupons-init-chromedriver` console script
- `config.py` — env-var vs INI-file account loading
- `accounts.py` — `Account` dataclass (username, password, mail_to, mail_from)
- `models.py` / `methods.py` — `Offer`, `OfferList`, `OfferStatus`, `OfferType`, `ClipRequest`, `ClipResponse` (all `dataclasses-json`)
- `email.py` — summary/error email composition + sendmail invocation
- `errors.py` — exception hierarchy: `Error`, `AuthenticationFailure`, `ClipError`, `HTTPError`, `TooManyClipErrors`
- `utils.py` — `yield_delay` request pacing helper

## Account configuration

Accounts come from exactly one of two sources (checked in this order; see `config.py` and the README):

- **Env vars (single account):** `SAFEWAY_ACCOUNT_USERNAME` (required), `SAFEWAY_ACCOUNT_PASSWORD` (required), `SAFEWAY_ACCOUNT_MAIL_FROM`, `SAFEWAY_ACCOUNT_MAIL_TO`.
- **INI file (one or more accounts):** passed via `-c/--accounts-config`. Optional top-level `email_sender = ...`; each `[safeway.<email>]` section needs `password = ...` and may set `notify = ...`.

Independent of account source, `SAFEWAY_HIGHLIGHT_KEYWORDS` (comma-separated, e.g. `FREE,BOGO`) restricts the per-offer listing in the success email to coupons whose `offer_price` matches any of the keywords (case-insensitive, word-boundary regex). Read in `app.py::main` and threaded through `SafewayCoupons` → `email_clip_results`.

The Docker image (`Dockerfile` + `docker/entrypoint`) wraps the CLI in cron and exposes the same env vars plus `CRON_SCHEDULE`, `SMTPHOST`, `SAFEWAY_ACCOUNTS_FILE`, `DEBUG_DIR`, `EXTRA_ARGS`.

## Conventions

- Black with `line-length = 79`, isort `profile = "black"` at the same width — keep imports and wrapping consistent.
- `disallow_untyped_defs = true` in mypy: every function (including tests) must be fully annotated.
- Pre-commit (`.pre-commit-config.yaml`) runs black, isort, autoflake, pyupgrade, flake8 (+ bugbear/simplify/pep8-naming), bandit, and mypy. `poetry run poe lint` runs the same set.
- HTTP tests use `responses` for mocking; `pytest-mock` for general mocking. Look at `tests/conftest.py` and `tests/utils.py` before adding fixtures.
- Selenium auth can be flaky against Safeway's WAF — when iterating on login code, prefer `--interactive-sign-in` and inspect screenshots saved under `--debug-dir` (`-D`) rather than guessing.
