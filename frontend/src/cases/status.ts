import type { CaseStatus } from '../api/types'

/** Suggestions stay hidden until analysis finishes. */
export function isAnalysing(status: CaseStatus): boolean {
  return status === 'new' || status === 'analysing'
}

/** A handler can decide after analysis and until closure. */
export function canDecide(status: CaseStatus): boolean {
  return status === 'awaiting_review' || status === 'needs_human_review' || status === 'in_progress'
}
