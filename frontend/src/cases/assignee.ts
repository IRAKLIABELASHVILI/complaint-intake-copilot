import type { CaseSummary } from '../api/types'

type Assignment = Pick<CaseSummary, 'assigned_to_user_id' | 'assigned_to_display_name'>

/** Who a case is assigned to, in words. A name can be missing for a user who no longer exists. */
export function assigneeLabel(assignment: Assignment): string {
  if (assignment.assigned_to_display_name) return assignment.assigned_to_display_name
  return assignment.assigned_to_user_id ? 'Assigned user unavailable' : 'Unassigned'
}
