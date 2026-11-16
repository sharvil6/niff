// Display helpers. Amounts arrive as YNAB milliunits (dollars × 1000, integers); everything here
// uses integer arithmetic so no balance ever passes through a floating-point fraction.

import type { Plan } from '@/api'

const MINUS = '−' // a real minus sign, the same width as the digits

/** -45000 → "−$45.00"; 1234567890 → "$1,234,567.89". Rounds half-cents away from zero. */
export function formatMilliunits(milliunits: number): string {
  if (!Number.isSafeInteger(milliunits)) {
    throw new RangeError(`not an integer milliunit amount: ${milliunits}`)
  }
  const abs = Math.abs(milliunits)
  const roundedUp = abs + 5
  const cents = (roundedUp - (roundedUp % 10)) / 10 // exact: divides a multiple of 10
  const dollars = (cents - (cents % 100)) / 100
  const grouped = String(dollars).replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  const sign = milliunits < 0 && cents > 0 ? MINUS : ''
  return `${sign}$${grouped}.${String(cents % 100).padStart(2, '0')}`
}

/** How long ago `then` was, coarsely: "just now", "12 min ago", "3 h ago", "2 days ago". */
export function formatAge(then: Date, now: Date): string {
  const minutes = Math.floor((now.getTime() - then.getTime()) / 60_000)
  if (minutes < 1) return 'just now' // includes small clock skew into the future
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours} h ago`
  const days = Math.floor(hours / 24)
  return days === 1 ? '1 day ago' : `${days} days ago`
}

/** Freshness of the whole snapshot, judged by its stalest plan so it never overstates. */
export function syncStatus(plans: Plan[], now: Date): string {
  if (plans.length === 0) return 'not synced yet'
  if (plans.some((plan) => plan.last_synced_at === null)) return 'some plans not synced yet'
  const oldest = Math.min(...plans.map((plan) => Date.parse(plan.last_synced_at ?? '')))
  return `updated ${formatAge(new Date(oldest), now)}`
}
