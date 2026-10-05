import { useAuditTrail } from '../../api/hooks'
import type { AuditEvent } from '../../api/types'
import { useCurrentUser } from '../../auth/authContext'
import { formatDateTime } from '../../shared/format'
import {
  AUDIT_SOURCE_LABELS,
  CATEGORY_LABELS,
  DECISION_LABELS,
  INDICATOR_LABELS,
  PRIORITY_LABELS,
  STATUS_LABELS,
  humanise,
} from '../../shared/labels'
import { ErrorMessage, Panel } from '../../shared/Layout'

/** Every change to the case, newest first (US-3.8). Read only: the API has no way to edit it. */
export function AuditTrail({ caseId }: { caseId: string }) {
  const audit = useAuditTrail(caseId)
  const me = useCurrentUser()

  return (
    <Panel title="Audit trail">
      {audit.isPending && <p>Loading…</p>}
      {audit.isError && <ErrorMessage error={audit.error} />}
      <ol className="audit">
        {audit.data?.map((event) => (
          <li key={event.id}>
            <time dateTime={event.created_at}>{formatDateTime(event.created_at)}</time>
            <span>
              <strong>{humanise(event.action)}</strong>
              {event.field && <> · {describeChange(event)}</>}
            </span>
            <span className="muted small">
              {AUDIT_SOURCE_LABELS[event.source]}
              {event.actor_user_id === null
                ? ' (system)'
                : event.actor_user_id === me.id
                  ? ' (you)'
                  : ' (a colleague)'}
            </span>
          </li>
        ))}
      </ol>
    </Panel>
  )
}

/** How each audited field and its values read to a person, rather than as the API's codes. */
const FIELD_LABELS: Record<string, { label: string; values?: Record<string, string> }> = {
  category: { label: 'Category', values: CATEGORY_LABELS },
  priority: { label: 'Priority', values: PRIORITY_LABELS },
  status: { label: 'Status', values: STATUS_LABELS },
  vulnerability_indicator: { label: 'Vulnerability indicator' },
  assigned_to_user_id: { label: 'Assigned to' },
}

function describeChange(event: AuditEvent): string {
  const field = event.field ?? ''
  const known = Object.hasOwn(FIELD_LABELS, field) ? FIELD_LABELS[field] : undefined
  const show = (value: unknown) => describeValue(value, known?.values)
  return `${known?.label ?? humanise(field)}: ${show(event.old_value)} → ${show(event.new_value)}`
}

/**
 * Audit values are JSON: a code, null, or an object, e.g. {"id", "decision"} for an indicator,
 * {"id", "type"} for an added one, {"status", "reason"} for a failed analysis.
 */
function describeValue(value: unknown, labels?: Record<string, string>): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'string') return label(value, labels)
  if (typeof value === 'object') {
    const { decision, type, status, reason } = value as Record<string, unknown>
    if (typeof decision === 'string') return label(decision, DECISION_LABELS)
    if (typeof type === 'string') return label(type, INDICATOR_LABELS)
    if (typeof status === 'string') {
      const text = label(status, STATUS_LABELS)
      return typeof reason === 'string' ? `${text} (${reason})` : text
    }
  }
  return String(value)
}

function label(code: string, labels?: Record<string, string>): string {
  return labels && Object.hasOwn(labels, code) ? (labels[code] ?? code) : humanise(code)
}
