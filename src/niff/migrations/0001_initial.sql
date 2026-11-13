-- Mirror of YNAB accounts. YNAB is the source of truth: these rows can be rebuilt with a full
-- re-fetch. Amounts are integers in milliunits ($12.34 = 12340), matching YNAB.
CREATE TABLE accounts (
    id              INTEGER PRIMARY KEY,
    ynab_account_id TEXT    NOT NULL UNIQUE,
    name            TEXT    NOT NULL,
    type            TEXT    NOT NULL,
    on_budget       INTEGER NOT NULL CHECK (on_budget IN (0, 1)),
    closed          INTEGER NOT NULL DEFAULT 0 CHECK (closed IN (0, 1)),
    deleted         INTEGER NOT NULL DEFAULT 0 CHECK (deleted IN (0, 1)),
    balance         INTEGER NOT NULL,
    source          TEXT    NOT NULL DEFAULT 'ynab' CHECK (source IN ('ynab', 'price', 'human')),
    updated_at      TEXT    NOT NULL
) STRICT;

-- Delta-sync cursor per data source. NULL server_knowledge means "never synced: full fetch".
CREATE TABLE sync_state (
    source           TEXT PRIMARY KEY,
    server_knowledge INTEGER,
    last_synced_at   TEXT
) STRICT;
