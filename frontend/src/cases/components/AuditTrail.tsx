import { useAuditTrail, useUsers } from '../../api/hooks'
import type { AuditEvent } from '../../api/types'
import { useCurrentUser } from '../../auth/authContext'
import { formatDateTime } from '../../shared/format'
import {
  AUDIT_SOURCE_LABELS,
  CATEGORY_LABELS,
  DECISION_LABELS,
  INDICATOR_LABELS,
  PRIORITY_LABELS,
  RESOLUTION_LABELS,
  STATUS_LABELS,
  humanise,
} from '../../shared/labels'
import { ErrorMessage, Panel } from '../../shared/Layout'

/** Every change to the case, newest first (US-3.8). Read only: the API has no way to edit it. */
export function AuditTrail({ caseId }: { caseId: string }) {
  const audit = useAuditTrail(caseId)
  const users = useUsers()
  const me = useCurrentUser()
  const names: Names = Object.fromEntries(
    (users.data ?? []).map((user) => [user.id, user.display_name]),
  )

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
              {event.field ? <> · {describeChange(event, names)}</> : <EventNote event={event} />}
            </span>
            <span className="muted small">{describeActor(event, me.id, names)}</span>
          </li>
        ))}
      </ol>
    </Panel>
  )
}

/** User id -> display name, for the people of this organisation. */
type Names = Record<string, string>

/** A comment, or the reason given for a handover, with who received the case. */
function EventNote({ event }: { event: AuditEvent }) {
  const value = event.new_value
  if (value === null || typeof value !== 'object' || !('note' in value)) return null
  const handedTo = 'assignee' in value ? `Handed to ${String(value.assignee)}: ` : ''
  return (
    <p className="complaint-body">
      {handedTo}
      {String(value.note)}
    </p>
  )
}

/**
 * Who acted, then how the decision relates to the AI when it does (accepted or overrode it).
 * `source` is not a person: a case a colleague created has source "system".
 */
function describeActor(event: AuditEvent, myId: string, names: Names): string {
  if (event.actor_user_id === null) return 'System'
  const who =
    event.actor_user_id === myId ? 'You' : (names[event.actor_user_id] ?? 'A colleague')
  const relatesToAi = event.source === 'accepted_suggestion' || event.source === 'override'
  return relatesToAi ? `${who} · ${AUDIT_SOURCE_LABELS[event.source]}` : who
}

/** How each audited field and its values read to a person, rather than as the API's codes. */
const FIELD_LABELS: Record<string, { label: string; values?: Record<string, string> }> = {
  category: { label: 'Category', values: CATEGORY_LABELS },
  priority: { label: 'Priority', values: PRIORITY_LABELS },
  status: { label: 'Status', values: STATUS_LABELS },
  vulnerability_indicator: { label: 'Vulnerability indicator' },
  assigned_to_user_id: { label: 'Assigned to' },
}

function describeChange(event: AuditEvent, names: Names): string {
  const field = event.field ?? ''
  const known = Object.hasOwn(FIELD_LABELS, field) ? FIELD_LABELS[field] : undefined
  // An assignment stores user ids: show the person, or "a colleague" for an unknown id.
  const values = field === 'assigned_to_user_id' ? names : known?.values
  const show = (value: unknown) =>
    values === names && typeof value === 'string' && !Object.hasOwn(names, value)
      ? 'a colleague'
      : describeValue(value, values)
  return `${known?.label ?? humanise(field)}: ${show(event.old_value)} → ${show(event.new_value)}`
}

/**
 * Audit values are JSON: a code, null, or an object, e.g. {"id", "decision"} for an indicator,
 * {"id", "type"} for an added one, {"status", "reason"} for a failed analysis,
 * {"status", "resolution_type", "note"} for a closure.
 */
function describeValue(value: unknown, labels?: Record<string, string>): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'string') return label(value, labels)
  if (typeof value === 'object') {
    const { decision, type, status, reason, note, resolution_type } = value as Record<
      string,
      unknown
    >
    if (typeof decision === 'string') return label(decision, DECISION_LABELS)
    if (typeof type === 'string') return label(type, INDICATOR_LABELS)
    if (typeof status === 'string') {
      const text = label(status, STATUS_LABELS)
      if (typeof note === 'string') {
        return `${text} (${label(String(resolution_type), RESOLUTION_LABELS)}): ${note}`
      }
      return typeof reason === 'string' ? `${text} (${reason})` : text
    }
  }
  return String(value)
}

function label(code: string, labels?: Record<string, string>): string {
  return labels && Object.hasOwn(labels, code) ? (labels[code] ?? code) : humanise(code)
}
