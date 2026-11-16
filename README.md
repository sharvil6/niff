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

## Web page

The page lives in `web/` (React, Vite, TypeScript, Tailwind and shadcn/ui components in
`web/src/components/ui/`). It needs Node 26. FastAPI serves the built page at `/`; API routes are
under `/api`, and `/healthz` stays at the root.

```bash
cd web && npm ci                 # install from package-lock.json
npm run dev                      # page on http://localhost:5173, /api goes to uvicorn on :8000
npm run build                    # build into web/dist, then uvicorn serves it on :8000
npm run typecheck && npm test    # strict type check + vitest
npx shadcn@latest add <name>     # copy another shadcn component into src/components/ui/
```

Without a build, the API still runs; `/` just returns 404.

## Syncing YNAB locally

Copy `.env.example` to `.env.local` (git-ignored) and put your YNAB personal access token in it.
uv loads the file for each command:

```bash
uv run --env-file .env.local niff plans   # find plan IDs, list them in NIFF_YNAB_PLAN_IDS
uv run --env-file .env.local niff sync    # one sync into data/niff.db
uv run --env-file .env.local uvicorn niff.main:app --reload   # API, page, hourly sync
```

`.env.local` holds a real secret in plain text: keep it out of the repo (it's git-ignored) and
readable only by you (`chmod 600 .env.local`).

## Running in a container

The `Dockerfile` builds the page with Node, installs Niff with uv and runs it with uvicorn as a
non-root user. `compose.yaml` runs it locally (Docker Desktop or OrbStack), reading the token and
plan IDs from `.env.local` and keeping the database in the `niff-data` volume:

```bash
docker compose up --build        # http://127.0.0.1:8000, sync logs in the output
docker compose down              # stop; the niff-data volume keeps the database
```

The volume starts empty; the first sync fills it from YNAB. `.dockerignore` is an allowlist, so
`.env.local`, `data/` and `private/` never reach the image. Set `NIFF_LOG_LEVEL` (default `INFO`)
to change how much Niff logs.

## Running on your tailnet

`compose.tailscale.yaml` adds a Tailscale sidecar so Niff is reachable over HTTPS from your
devices on your tailnet and nowhere else. Niff shares the sidecar's network stack and has no host
port; Tailscale Serve (`tailscale/serve.json`) terminates HTTPS on 443 and proxies to Niff on the
shared localhost. Niff has no login yet, so your tailnet policy is the only access control.

One-time setup in the Tailscale admin console:

1. DNS: turn on MagicDNS and HTTPS certificates. Certificates are published in public
   Certificate Transparency logs, so pick a tailnet DNS name that doesn't identify you.
2. Access controls: add `tag:niff` to `tagOwners`, and a rule that lets only your household's
   users reach `tag:niff` on port 443.
3. Keys: generate a reusable, pre-approved auth key with the tag `tag:niff`.

Copy `.env.tailscale.example` to `.env.tailscale` (git-ignored, `chmod 600`), put the key in it,
then:

```bash
docker compose -f compose.yaml -f compose.tailscale.yaml up --build
```

Open `https://niff.<your-tailnet>.ts.net`; the first request may take a few seconds while the
certificate is issued. The `tailscale-state` volume keeps the node's identity, so the key is used
only on first start. The YNAB token stays in `.env.local` and only the Niff container sees it.
