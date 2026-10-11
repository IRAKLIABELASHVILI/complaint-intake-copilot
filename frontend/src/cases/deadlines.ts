/** How a deadline reads to a handler. The numbers come from the API's deadline engine. */
import type { DeadlineProgress } from '../api/types'
import { plural } from '../shared/format'

export type Urgency = 'overdue' | 'due-soon' | 'ok'

/** The dashboard's "at risk" rule (backend: app/domain/deadline_risk.py), so a case counted as
 * at risk there is marked "due soon" here. */
export const AT_RISK_BUSINESS_DAYS = 2

/** 0 = due today. Negative = overdue (from the API). */
export function urgencyOf(progress: DeadlineProgress): Urgency {
  if (progress.is_overdue) return 'overdue'
  return progress.business_days_remaining <= AT_RISK_BUSINESS_DAYS ? 'due-soon' : 'ok'
}

export function deadlineText(progress: DeadlineProgress): string {
  const days = progress.business_days_remaining
  if (progress.is_overdue) return `Overdue by ${plural(-days, 'business day')}`
  if (days === 0) return 'Due today'
  return `${plural(days, 'business day')} left`
}
