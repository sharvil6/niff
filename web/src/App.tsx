import { useCallback, useEffect, useState } from 'react'

import { type Account, fetchSnapshot, type Milliunits, type Plan, type Snapshot } from '@/api'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { formatMilliunits, syncStatus } from '@/format'
import { cn } from '@/lib/utils'

type State = { kind: 'loading' } | { kind: 'error' } | { kind: 'ready'; snapshot: Snapshot }

export default function App() {
  const [state, setState] = useState<State>({ kind: 'loading' })
  const [attempt, setAttempt] = useState(0)
  const now = useNow()

  useEffect(() => {
    const controller = new AbortController()
    fetchSnapshot(controller.signal).then(
      (snapshot) => setState({ kind: 'ready', snapshot }),
      () => {
        if (!controller.signal.aborted) setState({ kind: 'error' })
      },
    )
    return () => controller.abort()
  }, [attempt])

  const retry = useCallback(() => {
    setState({ kind: 'loading' })
    setAttempt((n) => n + 1)
  }, [])

  return (
    <main className="mx-auto flex max-w-xl flex-col gap-4 p-4 pb-10">
      {state.kind === 'loading' && <Loading />}
      {state.kind === 'error' && (
        <Alert variant="destructive">
          <AlertTitle>Couldn't load your snapshot</AlertTitle>
          <AlertDescription>
            <p>Niff's server didn't answer. Check that it's running, then try again.</p>
            <Button variant="outline" size="sm" className="mt-2" onClick={retry}>
              Retry
            </Button>
          </AlertDescription>
        </Alert>
      )}
      {state.kind === 'ready' && <SnapshotView snapshot={state.snapshot} now={now} />}
    </main>
  )
}

function SnapshotView({ snapshot, now }: { snapshot: Snapshot; now: Date }) {
  return (
    <>
      <Card>
        <CardHeader>
          <CardDescription>Net worth</CardDescription>
          <CardTitle className="text-4xl">
            <Amount value={snapshot.net_worth} />
          </CardTitle>
          <CardDescription>{syncStatus(snapshot.plans, now)}</CardDescription>
        </CardHeader>
      </Card>
      {snapshot.plans.length === 0 && (
        <p className="text-muted-foreground px-1 text-sm">
          No YNAB data yet. Run a sync and refresh this page.
        </p>
      )}
      {snapshot.plans.map((plan) => (
        <PlanCard
          key={plan.id}
          plan={plan}
          accounts={snapshot.accounts.filter((a) => a.plan_id === plan.id)}
        />
      ))}
    </>
  )
}

function PlanCard({ plan, accounts }: { plan: Plan; accounts: Account[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{plan.name}</CardTitle>
        <CardAction className="font-medium">
          <Amount value={plan.total} />
        </CardAction>
      </CardHeader>
      <CardContent>
        <ul className="divide-border divide-y">
          {accounts.map((account) => (
            <li key={account.id} className="flex items-baseline justify-between gap-4 py-2">
              <span className="truncate">{account.name}</span>
              <Amount value={account.balance} />
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  )
}

function Amount({ value }: { value: Milliunits }) {
  return (
    <span className={cn('tabular-nums whitespace-nowrap', value < 0 && 'text-destructive/85')}>
      {formatMilliunits(value)}
    </span>
  )
}

function Loading() {
  return (
    <>
      <Skeleton className="h-32 rounded-xl" />
      <Skeleton className="h-48 rounded-xl" />
    </>
  )
}

/** The current time, refreshed every minute so "updated … ago" stays true. */
function useNow(): Date {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 60_000)
    return () => clearInterval(timer)
  }, [])
  return now
}
