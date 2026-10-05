/**
 * Human labels for the API's codes. `Record<Union, string>` makes the compiler insist on a label
 * for every value: if the backend adds a category, the frontend fails to build until it has one.
 */
import type {
  AuditEvent,
  CaseStatus,
  Category,
  IndicatorDecision,
  IndicatorType,
  Priority,
  VulnerabilityDriver,
} from '../api/types'

export const STATUS_LABELS: Record<CaseStatus, string> = {
  new: 'New',
  analysing: 'Analysing',
  awaiting_review: 'Awaiting review',
  needs_human_review: 'Needs human review',
  in_progress: 'In progress',
  resolved: 'Resolved',
}

export const CATEGORY_LABELS: Record<Category, string> = {
  fees_and_charges: 'Fees and charges',
  service_quality: 'Service quality',
  account_administration: 'Account administration',
  payments_and_transfers: 'Payments and transfers',
  lending_and_affordability: 'Lending and affordability',
  fraud_and_scams: 'Fraud and scams',
  advice_and_mis_selling: 'Advice and mis-selling',
  collections_and_arrears: 'Collections and arrears',
  other: 'Other',
}

export const PRIORITY_LABELS: Record<Priority, string> = {
  low: 'Low',
  medium: 'Medium',
  high: 'High',
  urgent: 'Urgent',
}

export const INDICATOR_LABELS: Record<IndicatorType, string> = {
  physical_illness: 'Physical illness',
  mental_health: 'Mental health',
  disability: 'Disability',
  bereavement: 'Bereavement',
  relationship_breakdown: 'Relationship breakdown',
  job_loss: 'Job loss',
  financial_hardship: 'Financial hardship',
  low_capability: 'Low capability',
}

export const DRIVER_LABELS: Record<VulnerabilityDriver, string> = {
  health: 'Health',
  life_events: 'Life events',
  resilience: 'Resilience',
  capability: 'Capability',
}

export const DECISION_LABELS: Record<IndicatorDecision, string> = {
  pending: 'Pending',
  confirmed: 'Confirmed',
  rejected: 'Rejected',
}

export const AUDIT_SOURCE_LABELS: Record<AuditEvent['source'], string> = {
  system: 'System',
  accepted_suggestion: 'Accepted AI suggestion',
  override: 'Overrode AI suggestion',
  handler: 'Handler',
}

/** Every value of a label map, in order: for <select> options. */
export function optionsOf<Key extends string>(labels: Record<Key, string>): [Key, string][] {
  return Object.entries(labels) as [Key, string][]
}

export function humanise(code: string): string {
  const text = code.replaceAll('_', ' ')
  return text.charAt(0).toUpperCase() + text.slice(1)
}

/** Only accept real statuses from the URL; anything else means "all". `Object.hasOwn`, not `in`:
 * `"toString" in STATUS_LABELS` is true, because `in` also sees inherited properties. */
export function parseStatus(value: string | null): CaseStatus | null {
  return value !== null && Object.hasOwn(STATUS_LABELS, value) ? (value as CaseStatus) : null
}
