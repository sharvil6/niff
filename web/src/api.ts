// Client for Niff's API. Types are written by hand to match the Pydantic response models in
// src/niff/main.py; keep the two in step when either changes.

/** Amounts are YNAB milliunits: integer dollars × 1000, negative for cards and loans. */
export type Milliunits = number

export type Account = {
  id: string
  plan_id: string
  name: string
  type: string
  on_budget: boolean
  balance: Milliunits
}

export type Plan = {
  id: string
  name: string
  last_synced_at: string | null // ISO 8601, UTC
  total: Milliunits
}

export type Snapshot = {
  net_worth: Milliunits
  plans: Plan[]
  accounts: Account[]
}

export async function fetchSnapshot(signal?: AbortSignal): Promise<Snapshot> {
  const response = await fetch('/api/snapshot', { signal })
  if (!response.ok) {
    throw new Error(`snapshot request failed: ${response.status}`)
  }
  return (await response.json()) as Snapshot
}
