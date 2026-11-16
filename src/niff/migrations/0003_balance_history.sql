-- One balance per open account per day, for the net worth trend. Each sync overwrites today's
-- rows, so a day keeps the last balance seen that day. "Day" is the date in NIFF_TIMEZONE.
-- Unlike accounts, this can't be rebuilt from YNAB: its API has no past balances.
CREATE TABLE balance_history (
    account_id  INTEGER NOT NULL REFERENCES accounts (id),
    date        TEXT    NOT NULL,  -- YYYY-MM-DD
    balance     INTEGER NOT NULL,  -- milliunits
    source      TEXT    NOT NULL CHECK (source IN ('ynab', 'price', 'human')),
    recorded_at TEXT    NOT NULL,
    PRIMARY KEY (account_id, date)
) STRICT, WITHOUT ROWID;
