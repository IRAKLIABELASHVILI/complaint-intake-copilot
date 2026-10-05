import { describe, expect, it } from 'vitest'

import { formatDateTime } from './format'
import { STATUS_LABELS, humanise, optionsOf, parseStatus } from './labels'

describe('parseStatus', () => {
  it('accepts every real status', () => {
    for (const status of Object.keys(STATUS_LABELS)) expect(parseStatus(status)).toBe(status)
  })

  it.each([null, '', 'closed', 'toString', 'constructor', '__proto__'])(
    'treats %j as "all statuses"',
    (value) => {
      // `in` would accept inherited names like "toString"; Object.hasOwn does not.
      expect(parseStatus(value)).toBeNull()
    },
  )
})

describe('labels', () => {
  it('lists options in order with their labels', () => {
    expect(optionsOf({ low: 'Low', high: 'High' })).toEqual([
      ['low', 'Low'],
      ['high', 'High'],
    ])
  })

  it('humanises codes', () => {
    expect(humanise('analysis_started')).toBe('Analysis started')
  })
})

describe('dates', () => {
  it('shows UK time, whatever the computer is set to', () => {
    // 16:00 UTC in October is 17:00 in London (BST): the SRC close of business.
    expect(formatDateTime('2026-10-06T16:00:00Z')).toBe('6 Oct 2026, 17:00')
  })

  it('shows a dash instead of crashing on a bad date', () => {
    expect(formatDateTime('not a date')).toBe('—')
  })
})
