import type { CaseStatus, DeadlineProgress } from '../../api/types'
import { plural } from '../../shared/format'
import { STATUS_LABELS } from '../../shared/labels'
import { deadlineText, urgencyOf } from '../deadlines'

export function StatusBadge({ status }: { status: CaseStatus }) {
  return <span className={`badge status-${status}`}>{STATUS_LABELS[status]}</span>
}

export function DeadlineBadge({ progress }: { progress: DeadlineProgress | null | undefined }) {
  if (!progress) return <span className="muted">—</span>
  return <span className={`badge deadline-${urgencyOf(progress)}`}>{deadlineText(progress)}</span>
}

export function FlagCount({ count }: { count: number }) {
  if (count === 0) return <span className="muted">—</span>
  return (
    <span className="badge flag" title="Open vulnerability indicators">
      {plural(count, 'flag')}
    </span>
  )
}
