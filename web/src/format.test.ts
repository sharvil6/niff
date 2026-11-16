import { describe, expect, it } from 'vitest'

import type { Plan } from '@/api'
import { formatAge, formatMilliunits, syncStatus } from '@/format'

describe('formatMilliunits', () => {
  it.each([
    [0, '$0.00'],
    [10, '$0.01'],
    [-45_000, '−$45.00'],
    [1_234_560, '$1,234.56'],
    [1_000_000_000, '$1,000,000.00'],
    [-123_456_789_010, '−$123,456,789.01'],
    [999_990, '$999.99'],
  ])('%i → %s', (milliunits, expected) => {
    expect(formatMilliunits(milliunits)).toBe(expected)
  })

  it('rounds half-cents away from zero', () => {
    expect(formatMilliunits(1_005)).toBe('$1.01')
    expect(formatMilliunits(-1_005)).toBe('−$1.01')
    expect(formatMilliunits(1_004)).toBe('$1.00')
  })

  it('does not show a minus sign on an amount that rounds to zero', () => {
    expect(formatMilliunits(-4)).toBe('$0.00')
  })

  it('rejects non-integer amounts', () => {
    expect(() => formatMilliunits(1.5)).toThrow(RangeError)
    expect(() => formatMilliunits(Number.NaN)).toThrow(RangeError)
  })
})

describe('formatAge', () => {
  const now = new Date('2026-01-15T12:00:00Z')
  const ago = (ms: number) => new Date(now.getTime() - ms)
  const minute = 60_000

  it.each([
    [0, 'just now'],
    [59_999, 'just now'],
    [-5 * minute, 'just now'],
    [minute, '1 min ago'],
    [59 * minute, '59 min ago'],
    [60 * minute, '1 h ago'],
    [23 * 60 * minute + 59 * minute, '23 h ago'],
    [24 * 60 * minute, '1 day ago'],
    [3 * 24 * 60 * minute, '3 days ago'],
  ])('%i ms ago → %s', (ms, expected) => {
    expect(formatAge(ago(ms), now)).toBe(expected)
  })
})

describe('syncStatus', () => {
  const now = new Date('2026-01-15T12:00:00Z')
  const plan = (last_synced_at: string | null): Plan => ({
    id: 'fake-plan-id',
    name: 'Example Household',
    last_synced_at,
    total: 0,
  })

  it('uses the stalest plan', () => {
    const plans = [plan('2026-01-15T11:55:00Z'), plan('2026-01-15T09:00:00Z')]
    expect(syncStatus(plans, now)).toBe('updated 3 h ago')
  })

  it('says when nothing or only some plans have synced', () => {
    expect(syncStatus([], now)).toBe('not synced yet')
    expect(syncStatus([plan('2026-01-15T11:55:00Z'), plan(null)], now)).toBe(
      'some plans not synced yet',
    )
  })
})
