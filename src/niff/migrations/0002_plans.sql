-- Accounts become plan-scoped, and YNAB's delta cursor (which is per plan) moves onto the plan.
-- accounts is a rebuildable mirror of YNAB, so it's recreated empty: SQLite can't add a required
-- foreign-key column to an existing table. The next sync of each plan is a full fetch.
DROP TABLE accounts;
DROP TABLE sync_state;

CREATE TABLE ynab_plans (
    id               INTEGER PRIMARY KEY,
    ynab_plan_id     TEXT    NOT NULL UNIQUE,
    name             TEXT    NOT NULL,
    server_knowledge INTEGER,  -- NULL until the first sync: means "full fetch"
    last_synced_at   TEXT
) STRICT;

CREATE TABLE accounts (
    id              INTEGER PRIMARY KEY,
    plan_id         INTEGER NOT NULL REFERENCES ynab_plans (id),
    ynab_account_id TEXT    NOT NULL UNIQUE,
    name            TEXT    NOT NULL,
    type            TEXT    NOT NULL,
    on_budget       INTEGER NOT NULL CHECK (on_budget IN (0, 1)),
    closed          INTEGER NOT NULL DEFAULT 0 CHECK (closed IN (0, 1)),
    deleted         INTEGER NOT NULL DEFAULT 0 CHECK (deleted IN (0, 1)),
    balance         INTEGER NOT NULL,  -- milliunits
    source          TEXT    NOT NULL DEFAULT 'ynab' CHECK (source IN ('ynab', 'price', 'human')),
    updated_at      TEXT    NOT NULL
) STRICT;
