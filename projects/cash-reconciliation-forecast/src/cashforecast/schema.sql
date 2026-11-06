CREATE TABLE IF NOT EXISTS datasets (
    id text PRIMARY KEY,
    imported_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS accounts (
    dataset_id text NOT NULL REFERENCES datasets(id),
    id text NOT NULL,
    currency text NOT NULL CHECK (currency IN ('CAD', 'USD')),
    balance_date date NOT NULL,
    bank_opening numeric(18,2) NOT NULL,
    ledger_opening numeric(18,2) NOT NULL,
    PRIMARY KEY (dataset_id, id)
);
CREATE TABLE IF NOT EXISTS entries (
    dataset_id text NOT NULL,
    source text NOT NULL CHECK (source IN ('bank', 'ledger')),
    id text NOT NULL,
    account text NOT NULL,
    posted_date date NOT NULL,
    amount numeric(18,2) NOT NULL,
    reference text NOT NULL,
    PRIMARY KEY (dataset_id, source, id),
    FOREIGN KEY (dataset_id, account) REFERENCES accounts(dataset_id, id)
);
CREATE INDEX IF NOT EXISTS entries_match_idx ON entries(dataset_id, account, posted_date, amount);
CREATE TABLE IF NOT EXISTS expected_flows (
    dataset_id text NOT NULL,
    id text NOT NULL,
    account text NOT NULL,
    due date NOT NULL,
    amount numeric(18,2) NOT NULL,
    description text NOT NULL,
    settled_bank_id text NOT NULL,
    PRIMARY KEY (dataset_id, id),
    FOREIGN KEY (dataset_id, account) REFERENCES accounts(dataset_id, id)
);
CREATE TABLE IF NOT EXISTS fx_rates (
    dataset_id text NOT NULL REFERENCES datasets(id),
    currency text NOT NULL,
    rate_date date NOT NULL,
    cad_per_unit numeric(12,6) NOT NULL CHECK (cad_per_unit > 0),
    PRIMARY KEY (dataset_id, currency, rate_date)
);
CREATE TABLE IF NOT EXISTS report_runs (
    id uuid PRIMARY KEY,
    dataset_id text NOT NULL REFERENCES datasets(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    as_of date NOT NULL,
    date_window integer NOT NULL,
    minimum_cad numeric(18,2) NOT NULL,
    result jsonb NOT NULL
);
