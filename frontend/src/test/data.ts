/** Test data in the API's exact shapes: the types make sure a fixture can never drift from it. */
import type { CaseDetail, CaseList, CaseSummary, Indicator, User } from '../api/types'

export const HANDLER: User = {
  id: 'u-1',
  tenant_id: 't-1',
  email: 'nina@example.com',
  display_name: 'Nina Handler',
  role: 'handler',
}

export const INDICATOR: Indicator = {
  id: 'i-1',
  indicator_type: 'bereavement',
  driver: 'life_events',
  evidence_quote: 'My husband passed away last month.',
  source: 'ai',
  decision: 'pending',
  decided_by_user_id: null,
  decided_at: null,
}

export function caseDetail(overrides: Partial<CaseDetail> = {}): CaseDetail {
  return {
    id: 'c-1',
    reference: 'CMP-2026-AAAA1111',
    external_message_id: null,
    subject: 'Charged a late fee',
    body: 'My husband passed away last month. You charged me a fee.',
    sender_email: 'jane@example.com',
    sender_name: 'Jane Doe',
    received_at: '2026-10-01T09:00:00Z',
    status: 'awaiting_review',
    assigned_to_user_id: null,
    src_deadline_at: '2026-10-06T16:00:00Z',
    final_response_deadline_at: '2026-11-26T23:59:59Z',
    final_category: null,
    final_priority: null,
    resolved_at: null,
    resolution_type: null,
    created_at: '2026-10-01T09:00:00Z',
    updated_at: '2026-10-01T09:00:00Z',
    deadline_tracking: {
      src: { deadline_at: '2026-10-06T16:00:00Z', business_days_remaining: 1, is_overdue: false },
      final_response: {
        deadline_at: '2026-11-26T23:59:59Z',
        business_days_remaining: 38,
        is_overdue: false,
      },
      resolved_in_time: null,
    },
    suggestion: {
      suggested_category: 'fees_and_charges',
      summary: 'Late fee charged after a bereavement.',
      suggested_priority: 'high',
      provider: 'fake',
      model: 'fake-keywords-v1',
      created_at: '2026-10-01T09:00:05Z',
    },
    review_reason: null,
    vulnerability_indicators: [INDICATOR],
    ...overrides,
  }
}

export function caseList(items: CaseSummary[], total = items.length): CaseList {
  return { items, total, limit: 25, offset: 0 }
}

export function summaryOf(detail: CaseDetail, openFlags = 0): CaseSummary {
  return {
    id: detail.id,
    reference: detail.reference,
    subject: detail.subject,
    sender_email: detail.sender_email,
    received_at: detail.received_at,
    status: detail.status,
    assigned_to_user_id: detail.assigned_to_user_id,
    src_deadline_at: detail.src_deadline_at,
    final_response_deadline_at: detail.final_response_deadline_at,
    deadline_tracking: detail.deadline_tracking,
    open_vulnerability_flags: openFlags,
  }
}
