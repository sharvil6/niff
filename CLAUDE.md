# Niff — working rules

## This repo is public

Niff manages a real household's finances, but its source is published as a portfolio project.
Everything committed — code, tests, fixtures, config, prompts, docs and commit metadata — must be
safe for anyone to read. Git history is permanent, so treat a leak as unfixable.

Never commit:

- Real financial data: transactions, balances, payees, amounts, budget or account IDs, or API
  responses recorded from a real account.
- Household specifics: account names, holdings (tickers, share counts), names of banks,
  brokerages, mortgage servicers or retirement portals.
- Network details: tailnet name, hostnames, IP addresses, Tailscale ACLs naming real devices.
- Personal details: names, email addresses, phone numbers.
- Secrets of any kind. Secrets live in 1Password and are loaded at runtime.

Instead:

- Tests use hand-written, obviously fake fixtures ("Coffee Shop", `-4500` milliunits).
- Household-specific config comes from 1Password or a git-ignored local file; the repo ships only
  `*.example` files with fake values.
- Real exports, notes and the full design doc live in `private/`, which is git-ignored.
- Commits use the GitHub no-reply email.

Before committing, review the staged diff against the list above. The pre-commit hook
(`.githooks/pre-commit`) runs gitleaks for secrets and checks staged changes against
`.private-denylist`, a git-ignored list of household-specific strings; neither replaces reading
the diff.

## Development

See `README.md` for commands. All checks (`ruff check`, `ruff format --check`, `pyright`,
`pytest`) must pass before a commit.
