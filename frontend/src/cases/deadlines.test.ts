import { describe, expect, it } from 'vitest'

import { deadlineText, urgencyOf } from './deadlines'

const progress = (business_days_remaining: number, is_overdue = false) => ({
  deadline_at: '2026-10-06T16:00:00Z',
  business_days_remaining,
  is_overdue,
})

describe('deadlines', () => {
  it.each([
    [progress(5), 'ok', '5 business days left'],
    [progress(2), 'ok', '2 business days left'],
    [progress(1), 'due-soon', '1 business day left'],
    [progress(0), 'due-soon', 'Due today'],
    [progress(-1, true), 'overdue', 'Overdue by 1 business day'],
    [progress(-3, true), 'overdue', 'Overdue by 3 business days'],
  ])('%j is %s: "%s"', (value, urgency, text) => {
    expect(urgencyOf(value)).toBe(urgency)
    expect(deadlineText(value)).toBe(text)
  })
})
