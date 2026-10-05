/** How a deadline reads to a handler. The numbers come from the API's deadline engine. */
import type { DeadlineProgress } from '../api/types'
import { plural } from '../shared/format'

export type Urgency = 'overdue' | 'due-soon' | 'ok'

/** 0 = due today, 1 = tomorrow: both need attention now. Negative = overdue (from the API). */
export function urgencyOf(progress: DeadlineProgress): Urgency {
  if (progress.is_overdue) return 'overdue'
  return progress.business_days_remaining <= 1 ? 'due-soon' : 'ok'
}

export function deadlineText(progress: DeadlineProgress): string {
  const days = progress.business_days_remaining
  if (progress.is_overdue) return `Overdue by ${plural(-days, 'business day')}`
  if (days === 0) return 'Due today'
  return `${plural(days, 'business day')} left`
}
