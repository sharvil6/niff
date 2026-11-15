# Niff

A private, self-hosted finance agent for a two-person household. See the design doc for the full picture.

## Development

Requires [uv](https://docs.astral.sh/uv/). uv installs Python 3.13 and the project's virtual environment on first use.

```bash
uv sync                          # create .venv from uv.lock
uv run uvicorn niff.main:app --reload   # dev server on http://127.0.0.1:8000 (DB: $NIFF_DB_PATH, default data/niff.db)
uv run pytest                    # tests
uv run ruff check . && uv run ruff format --check .   # lint + format
uv run pyright                   # type check
```

This repo is public; see `CLAUDE.md` for what must never be committed. Enable the pre-commit
hook once per clone (requires `brew install gitleaks`), then copy `.private-denylist.example` to
`.private-denylist` and fill in your own household strings:

```bash
git config core.hooksPath .githooks
```

## Syncing YNAB locally

Copy `.env.example` to `.env.local` (git-ignored) and put your YNAB personal access token in it.
uv loads the file for each command:

```bash
uv run --env-file .env.local niff plans   # find plan IDs, list them in NIFF_YNAB_PLAN_IDS
uv run --env-file .env.local niff sync    # one sync into data/niff.db
uv run --env-file .env.local uvicorn niff.main:app --reload   # API plus hourly sync
```

`.env.local` holds a real secret in plain text: keep it out of the repo (it's git-ignored) and
readable only by you (`chmod 600 .env.local`).
